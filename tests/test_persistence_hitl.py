"""M6 的 CI 安全测试：checkpoint 中断/恢复与审批路由，不联网。"""

from typing import TypedDict

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send, interrupt

from research_agent.config import settings
from research_agent.graph import build_graph, route_after_approval
from research_agent.nodes.approval import approval_node
from research_agent.persistence import sqlite_saver
from research_agent.state import Finding


@pytest.fixture
def hitl_on():
    old = settings.hitl_approval_enabled
    settings.hitl_approval_enabled = True
    yield
    settings.hitl_approval_enabled = old


def test_sqlite_saver_context(tmp_path) -> None:
    with sqlite_saver(str(tmp_path / "checkpoints.db")) as saver:
        assert saver is not None


def test_hitl_requires_checkpointer(hitl_on) -> None:
    with pytest.raises(ValueError):
        build_graph()


def test_approval_disabled_passes_through() -> None:
    old = settings.hitl_approval_enabled
    settings.hitl_approval_enabled = False
    try:
        assert approval_node({"query": "x"}) == {"_plan_rejected": False}
    finally:
        settings.hitl_approval_enabled = old


def test_approval_skips_on_replan(hitl_on) -> None:
    # 已在 critic 回流后的第二轮，不应再次打断人工。
    assert approval_node({"iterations": 1}) == {"_plan_rejected": False}


def test_route_after_approval() -> None:
    assert route_after_approval({"_aborted": True}) == END
    assert route_after_approval({"_plan_rejected": True}) == "planner"
    sends = route_after_approval({"subtasks": ["甲", "乙", "丙"]})
    assert len(sends) == 3
    assert all(isinstance(s, Send) for s in sends)


class _TinyState(TypedDict):
    value: str


def test_interrupt_and_resume_with_sqlite(tmp_path) -> None:
    """验证 checkpoint + interrupt + Command(resume) 的真实闭环。"""

    def ask(state: _TinyState) -> dict:
        decision = interrupt({"proposal": "ok?"})
        return {"value": (decision or {}).get("answer", "")}

    graph = StateGraph(_TinyState)
    graph.add_node("ask", ask)
    graph.add_edge(START, "ask")
    graph.add_edge("ask", END)

    config = {"configurable": {"thread_id": "tiny-1"}}
    with SqliteSaver.from_conn_string(str(tmp_path / "tiny.db")) as saver:
        app = graph.compile(checkpointer=saver)
        paused = app.invoke({"value": ""}, config=config)
        assert paused.get("__interrupt__")

        resumed = app.invoke(Command(resume={"answer": "yes"}), config=config)
        assert resumed["value"] == "yes"


class _FindingState(TypedDict):
    findings: list[Finding]


def test_checkpoint_serializes_finding(tmp_path) -> None:
    """Finding 必须能安全落盘并读回（显式注册 serde 模块）。"""

    def add(state: _FindingState) -> dict:
        return {"findings": [Finding(claim="x", source_url="https://a.com")]}

    graph = StateGraph(_FindingState)
    graph.add_node("add", add)
    graph.add_edge(START, "add")
    graph.add_edge("add", END)

    config = {"configurable": {"thread_id": "finding-1"}}
    with sqlite_saver(str(tmp_path / "finding.db")) as saver:
        app = graph.compile(checkpointer=saver)
        out = app.invoke({"findings": []}, config=config)
        assert out["findings"][0].claim == "x"

        snapshot = app.get_state(config)
        assert snapshot.values["findings"][0].source_url == "https://a.com"
