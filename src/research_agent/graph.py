"""多智能体研究图：规划、并行研究、反思、Claim-Evidence 核验与输出护栏。

当前链路：
    START → input_guard → planner → approval →（Send × N，并行 researcher）→ critic
                            ↑                                                │
                            └──────── 覆盖不足且未到上限 ────────────────────┘
                                                                             ↓
                                 synthesizer → verifier → output_guard → END
                                      ↑                        │
                                      └──────── 需修复 ────────┘

Planner 决定运行时开多少个研究员；findings 通过 reducer 跨并行分支累加；
Critic 判断覆盖是否充分；Synthesizer 生成 summary/sections/citations；
Verifier 把报告拆成原子断言并对照证据片段判断支持/矛盾/不足；
Output Guard 校验引用来源、内容安全与事实核验结果，不合格则有界重写一次。
approval 是人在回路闸门：仅在开启 HITL 且是首版计划时暂停。
"""

from __future__ import annotations

import argparse
import os
import uuid

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send

from research_agent.config import settings
from research_agent.guardrails import RETRY_POLICY
from research_agent.nodes.approval import approval_node
from research_agent.nodes.critic import critic_node
from research_agent.nodes.input_guard import input_guard_node
from research_agent.nodes.output_guard import output_guard_node
from research_agent.nodes.planner import planner_node
from research_agent.nodes.researcher import researcher_node
from research_agent.nodes.synthesizer import synthesizer_node
from research_agent.nodes.verifier import verifier_node
from research_agent.observability import traced
from research_agent.persistence import sqlite_saver
from research_agent.reporting import render_report_markdown
from research_agent.state import ResearchState


def route_to_researchers(state: ResearchState):
    """动态 fan-out：每个子任务发一个 Send，生成一个并行 researcher 分支。

    对照主蓝本 graph.py 的 route_to_researchers：返回 list[Send] 后，
    LangGraph 会在同一超步里并行执行这些分支；它们写给 findings 的值由
    `Annotated[..., add]` reducer 累加，不会互相覆盖。
    """
    if state.get("rejected"):
        return END
    tasks = state.get("subtasks") or []
    if not tasks:
        return END
    return [Send("researcher", {"subtasks": [task], "findings": []}) for task in tasks]


def route_after_input_guard(state: ResearchState) -> str:
    """输入不合法就直接结束，不进入任何模型调用。"""
    return END if state.get("rejected") else "planner"


def route_after_planner(state: ResearchState) -> str:
    """Planner 拒绝（问题太笼统）时直接结束，否则进入审批闸门。"""
    return END if state.get("rejected") else "approval"


def route_after_approval(state: ResearchState):
    """审批后：中止→END；打回→planner；通过/修改→继续 fan-out。"""
    if state.get("_aborted"):
        return END
    if state.get("_plan_rejected"):
        return "planner"
    return route_to_researchers(state)


def route_after_critic(state: ResearchState) -> str:
    """三重判断：已充分 / 迭代到顶 / 预算花完，任一成立就收尾。

    否则回流 planner 补研——这就是图里的「反思循环」。
    双重封顶保证它不会无限循环：迭代次数与 LLM 调用预算是两道闸。
    """
    iterations = state.get("iterations", 0)
    remaining = settings.max_llm_calls_per_run - state.get("llm_calls", 0)
    if (
        state.get("_sufficient")
        or iterations >= settings.max_research_iterations
        or remaining < settings.min_calls_for_next_round
    ):
        return "synthesizer"
    return "planner"


def route_after_researchers(state: ResearchState) -> str:
    """搜索服务不可用时不继续烧模型调用，直接给出基础设施错误。"""
    return "fail" if state.get("infrastructure_error") else "critic"


def fail_node(state: ResearchState) -> dict:
    reason = state.get("infrastructure_error") or "检索服务不可用"
    return {
        "report": {
            "summary": f"检索服务不可用：{reason}",
            "sections": [],
            "citations": [],
        }
    }


def route_after_output_guard(state: ResearchState) -> str:
    """引用/内容校验不合格时回到 synthesizer 修复；否则交卷。"""
    return "synthesizer" if state.get("_needs_repair") else END


def route_after_synthesizer(state: ResearchState) -> str:
    """开启核验时先过 Verifier，否则直接交给输出护栏。"""
    return "verifier" if settings.enable_verifier else "output_guard"


def build_graph(checkpointer=None):
    """组装并编译研究图。"""
    if settings.hitl_approval_enabled and checkpointer is None:
        raise ValueError(
            "HITL 审批需要 checkpointer：请用 sqlite_saver() 创建图后再编译。"
        )
    graph = StateGraph(ResearchState)
    graph.add_node("input_guard", traced("input_guard")(input_guard_node))
    graph.add_node("planner", traced("planner")(planner_node), retry_policy=RETRY_POLICY)
    graph.add_node("approval", approval_node)
    graph.add_node(
        "researcher", traced("researcher")(researcher_node), retry_policy=RETRY_POLICY
    )
    graph.add_node("critic", traced("critic")(critic_node), retry_policy=RETRY_POLICY)
    graph.add_node("fail", traced("fail")(fail_node))
    graph.add_node(
        "synthesizer", traced("synthesizer")(synthesizer_node), retry_policy=RETRY_POLICY
    )
    graph.add_node("verifier", traced("verifier")(verifier_node), retry_policy=RETRY_POLICY)
    graph.add_node("output_guard", traced("output_guard")(output_guard_node))

    graph.add_edge(START, "input_guard")
    graph.add_conditional_edges("input_guard", route_after_input_guard, ["planner", END])
    graph.add_conditional_edges("planner", route_after_planner, ["approval", END])
    graph.add_conditional_edges("approval", route_after_approval, ["planner", "researcher", END])
    graph.add_conditional_edges("researcher", route_after_researchers, ["critic", "fail"])
    graph.add_edge("fail", END)
    graph.add_conditional_edges("critic", route_after_critic, ["planner", "synthesizer"])
    graph.add_conditional_edges(
        "synthesizer", route_after_synthesizer, ["verifier", "output_guard"]
    )
    graph.add_edge("verifier", "output_guard")
    graph.add_conditional_edges("output_guard", route_after_output_guard, ["synthesizer", END])
    return graph.compile(checkpointer=checkpointer)


def _ask_human(payload: dict, forced: str = "") -> dict:
    """在命令行里展示待审批计划，返回 interrupt 期望的 decision。"""
    if forced == "approve":
        return {"action": "approve"}
    if forced == "abort":
        return {"action": "abort", "reason": "命令行指定中止"}

    print("\n⏸  图已暂停，等待人工审批。")
    print("问题：", payload.get("query"))
    print("建议的子任务：")
    for i, task in enumerate(payload.get("proposed_subtasks", []), 1):
        print(f"  {i}. {task}")
    choice = input("\n决策 [approve/edit/reject/abort]（默认 approve）：").strip().lower()
    if choice == "edit":
        raw = input("新的子任务（用逗号分隔）：")
        tasks = [s.strip() for s in raw.split(",") if s.strip()]
        return {"action": "edit", "subtasks": tasks}
    if choice == "reject":
        return {"action": "reject", "feedback": input("给规划器的反馈：").strip()}
    if choice == "abort":
        return {"action": "abort", "reason": input("中止原因（可选）：").strip()}
    return {"action": "approve"}


def run_graph(
    query: str | None,
    thread_id: str | None = None,
    hitl: bool = False,
    forced_decision: str = "",
) -> tuple[dict, str]:
    """新建或恢复一次运行；始终使用 SQLite checkpoint 以便断点续跑。"""
    if hitl:
        settings.hitl_approval_enabled = True
    tid = thread_id or f"run-{uuid.uuid4().hex[:8]}"
    config = {
        "configurable": {"thread_id": tid},
        "max_concurrency": 3,
    }
    with sqlite_saver() as saver:
        app = build_graph(checkpointer=saver)
        if query:
            result = app.invoke({"query": query}, config=config)
        else:
            snapshot = app.get_state(config)
            if not snapshot.next:
                return snapshot.values or {}, tid
            result = app.invoke(None, config=config)

        while result.get("__interrupt__"):
            decision = _ask_human(result["__interrupt__"][0].value, forced_decision)
            result = app.invoke(Command(resume=decision), config=config)
    return result, tid


def main() -> None:
    parser = argparse.ArgumentParser(description="多智能体深度研究 Agent")
    parser.add_argument("query", nargs="?", default="", help="研究问题")
    parser.add_argument("--thread", default="", help="按 thread_id 恢复运行")
    parser.add_argument("--hitl", action="store_true", help="开启人工审批闸门")
    parser.add_argument(
        "--decision",
        choices=["approve", "edit", "reject", "abort"],
        default="",
        help="无人值守时的审批决定（edit/reject 仍需交互输入细节）",
    )
    args = parser.parse_args()

    query = args.query.strip() or os.environ.get("M3_QUERY", "").strip()
    if not query and not args.thread:
        query = input("请输入你的研究问题：").strip()
    if not query and not args.thread:
        print("问题不能为空")
        return

    result, tid = run_graph(
        query or None,
        args.thread or None,
        args.hitl,
        args.decision,
    )
    print(f"\nthread_id: {tid}（恢复：--thread {tid}）")
    if result.get("rejected"):
        print("无法开始研究：", result.get("rejection_reason", "输入不合法"))
        return
    if result.get("_aborted"):
        print("研究已中止：", (result.get("report") or {}).get("summary", ""))
        return
    if result.get("infrastructure_error"):
        print("检索服务不可用：", result["infrastructure_error"])
        return
    print(render_report_markdown(result.get("report") or {}))
    if result.get("guardrail_flags"):
        print("⚠ 输出护栏标记：")
        for flag in result["guardrail_flags"]:
            print("  -", flag)
    print("\n子任务数：", len(result.get("subtasks", [])))
    print("发现数：", len(result.get("findings", [])))
    print("模型调用数：", result.get("llm_calls", 0))
    print("迭代轮数：", result.get("iterations", 0))
    print("覆盖是否充分：", result.get("_sufficient", False))
    print("输出修复次数：", result.get("repairs", 0))
    verification = result.get("verification") or {}
    if verification:
        print(
            "事实核验："
            f"支持 {verification.get('supported', 0)} / "
            f"矛盾 {verification.get('contradicted', 0)} / "
            f"证据不足 {verification.get('insufficient', 0)}"
        )


if __name__ == "__main__":
    main()
