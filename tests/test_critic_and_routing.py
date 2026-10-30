"""M4 的 CI 安全测试：反思循环的路由与预算封顶，不联网。"""

from research_agent.config import settings
from research_agent.graph import route_after_critic
from research_agent.nodes.critic import CriticVerdict


def test_stop_when_sufficient() -> None:
    state = {"_sufficient": True, "iterations": 1, "llm_calls": 5}
    assert route_after_critic(state) == "collect"


def test_loop_when_insufficient_and_under_caps() -> None:
    state = {"_sufficient": False, "iterations": 0, "llm_calls": 5}
    assert route_after_critic(state) == "planner"


def test_stop_at_iteration_cap() -> None:
    state = {
        "_sufficient": False,
        "iterations": settings.max_research_iterations,
        "llm_calls": 5,
    }
    assert route_after_critic(state) == "collect"


def test_stop_at_budget_cap() -> None:
    state = {
        "_sufficient": False,
        "iterations": 0,
        "llm_calls": settings.max_llm_calls_per_run,
    }
    assert route_after_critic(state) == "collect"


def test_critic_verdict_schema() -> None:
    verdict = CriticVerdict(sufficient=False, gaps=["缺少成本数据"], notes="证据不足")
    assert verdict.sufficient is False
    assert verdict.gaps == ["缺少成本数据"]
