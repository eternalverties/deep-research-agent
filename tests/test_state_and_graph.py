"""M2 的 CI 安全测试：不调用真实模型/网络。"""

import pytest
from pydantic import ValidationError

from research_agent.graph import build_graph
from research_agent.nodes.planner import ResearchPlan
from research_agent.state import Finding, ResearchState


def test_research_plan_requires_3_to_5_subtasks() -> None:
    with pytest.raises(ValidationError):
        ResearchPlan(subtasks=["只有两个", "子任务"])

    with pytest.raises(ValidationError):
        ResearchPlan(subtasks=[str(i) for i in range(6)])

    plan = ResearchPlan(subtasks=["一", "二", "三"])
    assert plan.subtasks == ["一", "二", "三"]


def test_state_reducers_are_accumulating() -> None:
    """findings / llm_calls 的 reducer 应该是 operator.add（可累加）。"""
    from operator import add
    from typing import get_type_hints

    # 注意：state.py 用了 `from __future__ import annotations`，注解在运行时是
    # 字符串/ForwardRef，必须用 get_type_hints(include_extras=True) 才能拿到
    # Annotated 里的 reducer 元数据。
    hints = get_type_hints(ResearchState, include_extras=True)
    finding_meta = hints["findings"].__metadata__
    calls_meta = hints["llm_calls"].__metadata__

    assert add in finding_meta
    assert add in calls_meta


def test_graph_compiles_without_network() -> None:
    app = build_graph()
    assert app is not None


def test_finding_model() -> None:
    f = Finding(claim="LangGraph 支持 checkpoint", source_url="https://example.com")
    assert f.source_url == "https://example.com"
