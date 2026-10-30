"""M3 的 CI 安全测试：验证动态 fan-out 的路由与 URL 提取，不联网。"""

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from research_agent.graph import route_to_researchers
from research_agent.nodes.researcher import extract_urls
from research_agent.state import Finding, ResearchState


def test_one_send_per_subtask() -> None:
    sends = route_to_researchers({"subtasks": ["甲", "乙", "丙"]})
    assert len(sends) == 3
    assert all(isinstance(s, Send) for s in sends)
    assert all(s.node == "researcher" for s in sends)
    assert [s.arg["subtasks"] for s in sends] == [["甲"], ["乙"], ["丙"]]


def test_empty_subtasks_routes_to_end() -> None:
    assert route_to_researchers({"subtasks": []}) == END


def test_extract_urls_dedupes_and_keeps_order() -> None:
    text = "见 https://a.com/x 和 https://b.com/y，再看 https://a.com/x。"
    assert extract_urls(text) == ["https://a.com/x", "https://b.com/y"]


def test_parallel_branches_accumulate_with_reducer() -> None:
    """用假 researcher 真正跑一遍 fan-out/fan-in，验证 reducer 不丢数据。"""

    def fake_researcher(state: dict) -> dict:
        task = state["subtasks"][0]
        return {
            "findings": [Finding(claim=f"发现-{task}", source_url=f"https://example.com/{task}")],
            "llm_calls": 1,
        }

    def route(state: dict):
        return [
            Send("researcher", {"subtasks": [task], "findings": []})
            for task in state.get("subtasks", [])
        ]

    def collect(state: dict) -> dict:
        return {"report": f"共 {len(state['findings'])} 条发现"}

    graph = StateGraph(ResearchState)
    graph.add_node("researcher", fake_researcher)
    graph.add_node("collect", collect)
    graph.add_conditional_edges(START, route, ["researcher"])
    graph.add_edge("researcher", "collect")
    graph.add_edge("collect", END)

    result = graph.compile().invoke(
        {"query": "测试", "subtasks": ["甲", "乙", "丙"], "findings": [], "llm_calls": 0}
    )

    assert len(result["findings"]) == 3
    assert result["llm_calls"] == 3
    assert {f.claim for f in result["findings"]} == {"发现-甲", "发现-乙", "发现-丙"}
    assert result["report"] == "共 3 条发现"
