"""搜索提供方降级的离线测试。"""

from research_agent.config import settings
from research_agent.tools import search
from research_agent.tools.search import web_search


class FakeTavily:
    def __init__(self, result):
        self.result = result

    def invoke(self, payload):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_auto_falls_back_on_quota_error(monkeypatch) -> None:
    monkeypatch.setattr(
        search,
        "_get_search",
        lambda: FakeTavily({"error": "Error 432: usage limit exceeded"}),
    )
    monkeypatch.setattr(
        search,
        "_duckduckgo_search",
        lambda query: {"provider": "duckduckgo", "results": [{"url": "https://a.com"}]},
    )
    monkeypatch.setattr(settings, "search_provider", "auto")

    result = web_search.invoke({"query": "测试"})
    assert result["provider"] == "duckduckgo"


def test_tavily_only_keeps_error(monkeypatch) -> None:
    monkeypatch.setattr(
        search,
        "_get_search",
        lambda: FakeTavily({"error": "Error 432: usage limit exceeded"}),
    )
    monkeypatch.setattr(settings, "search_provider", "tavily")

    result = web_search.invoke({"query": "测试"})
    assert "error" in result


def test_duckduckgo_provider_skips_tavily(monkeypatch) -> None:
    def should_not_call():
        raise AssertionError("Tavily should not be called")

    monkeypatch.setattr(search, "_get_search", should_not_call)
    monkeypatch.setattr(
        search,
        "_duckduckgo_search",
        lambda query: {"provider": "duckduckgo", "results": []},
    )
    monkeypatch.setattr(settings, "search_provider", "duckduckgo")

    result = web_search.invoke({"query": "测试"})
    assert result["provider"] == "duckduckgo"


def test_duckduckgo_result_normalization(monkeypatch) -> None:
    class FakeDDGS:
        def text(self, query, max_results):
            return [
                {
                    "title": "A",
                    "href": "https://a.com",
                    "body": "一段正文",
                }
            ]

    monkeypatch.setattr(search, "DDGS", FakeDDGS)
    result = search._duckduckgo_search("测试")
    assert result["results"][0]["url"] == "https://a.com"
    assert result["results"][0]["content"] == "一段正文"
