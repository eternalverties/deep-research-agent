"""M4 · 带反思闭环的多智能体研究图。

当前链路：
    START → planner →（Send × N，并行 researcher）→ critic
          ↑                                            │
          └──────── 覆盖不足且未到上限 ────────────────┘
                                                       ↓
                                                   collect → END

Planner 决定运行时「开多少个研究员」；每个 Send 携带一个子任务；
所有 researcher 分支结束后，findings 通过 reducer 汇总到父状态；
Critic 判断覆盖是否充分，不足则带着 gaps 回流 Planner 补研。
"""

from __future__ import annotations

import os
import sys

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from research_agent.config import settings
from research_agent.guardrails import RETRY_POLICY
from research_agent.nodes.critic import critic_node
from research_agent.nodes.input_guard import input_guard_node
from research_agent.nodes.planner import planner_node
from research_agent.nodes.researcher import researcher_node
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


def collect_node(state: ResearchState) -> dict:
    """fan-in 汇总节点（M5 会升级成带引用的 synthesizer）。"""
    findings = state.get("findings") or []
    grouped: dict[str, list[str]] = {}
    for item in findings:
        urls = grouped.setdefault(item.claim, [])
        if item.source_url and item.source_url not in urls:
            urls.append(item.source_url)

    lines: list[str] = []
    for claim, urls in grouped.items():
        lines.append(f"- {claim}")
        if urls:
            lines.append("  来源：" + "；".join(urls))
        else:
            lines.append("  来源：（未标注来源）")
    body = "\n".join(lines) if lines else "（没有找到可用的发现）"
    return {"report": "## 研究发现\n" + body}


def route_after_critic(state: ResearchState) -> str:
    """三重判断：已充分 / 迭代到顶 / 预算花完，任一成立就收尾。

    否则回流 planner 补研——这就是图里的「反思循环」。
    双重封顶保证它不会无限循环：迭代次数与 LLM 调用预算是两道闸。
    """
    iterations = state.get("iterations", 0)
    budget_spent = state.get("llm_calls", 0) >= settings.max_llm_calls_per_run
    if (
        state.get("_sufficient")
        or iterations >= settings.max_research_iterations
        or budget_spent
    ):
        return "collect"
    return "planner"


def build_graph(checkpointer=None):
    """组装并编译研究图。"""
    graph = StateGraph(ResearchState)
    graph.add_node("input_guard", input_guard_node)
    graph.add_node("planner", planner_node, retry_policy=RETRY_POLICY)
    graph.add_node("researcher", researcher_node, retry_policy=RETRY_POLICY)
    graph.add_node("critic", critic_node, retry_policy=RETRY_POLICY)
    graph.add_node("collect", collect_node)

    graph.add_edge(START, "input_guard")
    graph.add_conditional_edges("input_guard", route_after_input_guard, ["planner", END])
    graph.add_conditional_edges("planner", route_to_researchers, ["researcher", END])
    graph.add_edge("researcher", "critic")
    graph.add_conditional_edges("critic", route_after_critic, ["planner", "collect"])
    graph.add_edge("collect", END)
    return graph.compile(checkpointer=checkpointer)


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("M3_QUERY", "").strip()
    if not query:
        query = input("请输入你的研究问题：").strip()
    if not query:
        print("问题不能为空")
        return
    # 并发上限 3：既保留「并行」的效果，又避免一次打满连接导致网络抖动。
    result = build_graph().invoke({"query": query}, config={"max_concurrency": 3})
    if result.get("rejected"):
        print("无法开始研究：", result.get("rejection_reason", "输入不合法"))
        return
    print(result["report"])
    print("\n子任务数：", len(result.get("subtasks", [])))
    print("发现数：", len(result.get("findings", [])))
    print("模型调用数：", result.get("llm_calls", 0))
    print("迭代轮数：", result.get("iterations", 0))
    print("覆盖是否充分：", result.get("_sufficient", False))


if __name__ == "__main__":
    main()
