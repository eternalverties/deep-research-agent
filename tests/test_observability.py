"""本地执行轨迹的离线测试。"""

from research_agent.observability import traced


def test_traced_records_planner_event() -> None:
    @traced("planner")
    def node(state):
        return {"subtasks": ["甲", "乙"], "llm_calls": 1}

    result = node({"query": "测试"})
    event = result["trace"][0]
    assert event["node"] == "planner"
    assert event["llm_calls"] == 1
    assert "2 个子任务" in event["detail"]
    assert event["duration_ms"] >= 0


def test_traced_researcher_detail() -> None:
    @traced("researcher")
    def node(state):
        return {"findings": [1, 2], "evidence": [1], "llm_calls": 3}

    event = node({"subtasks": ["任务A"]})["trace"][0]
    assert "任务A" in event["detail"]
    assert "发现 2" in event["detail"]
    assert "证据 1" in event["detail"]


def test_traced_preserves_node_result() -> None:
    @traced("critic")
    def node(state):
        return {"_sufficient": True, "gaps": [], "llm_calls": 1}

    result = node({})
    assert result["_sufficient"] is True
    assert result["trace"][0]["node"] == "critic"
