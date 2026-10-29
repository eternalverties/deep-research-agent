"""M2 · 用 StateGraph 把「规划」这一步建模成图。

当前链路：START → planner →（条件路由）→ format_plan → END
M3 会把 format_plan 替换成「并行研究员 + critic + 综合报告」的完整子图。
"""

from __future__ import annotations

import sys

from langgraph.graph import END, START, StateGraph

from research_agent.nodes.planner import planner_node
from research_agent.state import ResearchState


def route_after_planner(state: ResearchState) -> str:
    """条件边：有子任务就进入整理节点，没有则直接结束。"""
    return "format_plan" if state.get("subtasks") else END


def format_plan_node(state: ResearchState) -> dict:
    """M2 的占位节点：把计划整理成一段文本，方便命令行查看。

    M3 之后这里会被 researcher / critic / synthesizer 取代，
    但它在当前里程碑让「图确实跑通了」有一个可见产物。
    """
    lines = [f"{i}. {task}" for i, task in enumerate(state["subtasks"], 1)]
    return {"report": "研究计划：\n" + "\n".join(lines)}


def build_graph(checkpointer=None):
    """组装并编译研究图。"""
    graph = StateGraph(ResearchState)
    graph.add_node("planner", planner_node)
    graph.add_node("format_plan", format_plan_node)

    graph.add_edge(START, "planner")
    graph.add_conditional_edges("planner", route_after_planner, ["format_plan", END])
    graph.add_edge("format_plan", END)
    return graph.compile(checkpointer=checkpointer)


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else input("请输入你的研究问题：").strip()
    if not query:
        print("问题不能为空")
        return
    result = build_graph().invoke({"query": query})
    print(result["report"])
    print("\n子任务数：", len(result.get("subtasks", [])))


if __name__ == "__main__":
    main()
