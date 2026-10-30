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
    monkeypatch.setattr(settings, "serper_api_key", "")
    monkeypatch.setattr(search, "_TAVILY_DISABLED", False)

    result = web_search.invoke({"query": "测试"})
    assert result["provider"] == "bing"


def test_auto_falls_back_to_serper(monkeypatch) -> None:
    monkeypatch.setattr(
        search,
        "_get_search",
        lambda: FakeTavily({"error": "Error 432: usage limit exceeded"}),
    )
    monkeypatch.setattr(
        search,
        "_serper_search",
        lambda query: {"provider": "serper", "results": [{"url": "https://a.com"}]},
    )
    monkeypatch.setattr(settings, "search_provider", "auto")
    monkeypatch.setattr(settings, "serper_api_key", "test")
    monkeypatch.setattr(search, "_TAVILY_DISABLED", False)

    result = web_search.invoke({"query": "测试"})
    assert result["provider"] == "serper"


def test_tavily_circuit_breaker(monkeypatch) -> None:
    calls = {"tavily": 0}

    class CountingTavily:
        def invoke(self, payload):
            calls["tavily"] += 1
            return {"error": "Error 432: usage limit exceeded"}

    monkeypatch.setattr(search, "_get_search", lambda: CountingTavily())
    monkeypatch.setattr(
        search,
        "_serper_search",
        lambda query: {"provider": "serper", "results": []},
    )
    monkeypatch.setattr(settings, "search_provider", "auto")
    monkeypatch.setattr(settings, "serper_api_key", "test")
    monkeypatch.setattr(search, "_TAVILY_DISABLED", False)

    assert web_search.invoke({"query": "第一次"})["provider"] == "serper"
    assert web_search.invoke({"query": "第二次"})["provider"] == "serper"
    assert calls["tavily"] == 1


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


def test_serper_result_normalization(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "organic": [
                    {
                        "title": "A",
                        "link": "https://a.com",
                        "snippet": "一段摘要",
                    },
                    {
                        "title": "Google Redirect",
                        "link": "https://www.google.com/goto?url=abc",
                        "snippet": "不应被采用",
                    },
                ]
            }

    monkeypatch.setattr(search.httpx, "post", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr(settings, "serper_api_key", "test")
    result = search._serper_search("测试")
    assert result["provider"] == "serper"
    assert len(result["results"]) == 1
    assert result["results"][0]["url"] == "https://a.com"
    assert result["results"][0]["content"] == "一段摘要"
