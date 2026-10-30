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
        "_bing_search",
        lambda query: {"provider": "bing", "results": [{"url": "https://a.com"}]},
    )
    monkeypatch.setattr(settings, "search_provider", "auto")

    result = web_search.invoke({"query": "测试"})
    assert result["provider"] == "bing"


def test_tavily_only_keeps_error(monkeypatch) -> None:
    monkeypatch.setattr(
        search,
        "_get_search",
        lambda: FakeTavily({"error": "Error 432: usage limit exceeded"}),
    )
    monkeypatch.setattr(settings, "search_provider", "tavily")

    result = web_search.invoke({"query": "测试"})
    assert "error" in result


def test_bing_provider_skips_tavily(monkeypatch) -> None:
    def should_not_call():
        raise AssertionError("Tavily should not be called")

    monkeypatch.setattr(search, "_get_search", should_not_call)
    monkeypatch.setattr(
        search,
        "_bing_search",
        lambda query: {"provider": "bing", "results": []},
    )
    monkeypatch.setattr(settings, "search_provider", "bing")

    result = web_search.invoke({"query": "测试"})
    assert result["provider"] == "bing"


def test_bing_result_normalization(monkeypatch) -> None:
    class FakeResponse:
        content = (
            '<?xml version="1.0"?><rss><channel><item>'
            "<title>A</title><link>https://a.com</link>"
            "<description><b>一段正文</b></description>"
            "</item></channel></rss>"
        ).encode()

        def raise_for_status(self):
            return None

    monkeypatch.setattr(search.httpx, "get", lambda *args, **kwargs: FakeResponse())
    result = search._bing_search("测试")
    assert result["results"][0]["url"] == "https://a.com"
    assert result["results"][0]["content"] == "一段正文"
