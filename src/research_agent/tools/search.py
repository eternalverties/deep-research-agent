"""联网搜索工具：Tavily 主提供方 + DuckDuckGo 免费降级。"""

from functools import lru_cache

from ddgs import DDGS
from langchain.tools import tool
from langchain_tavily import TavilySearch

from research_agent.config import settings


@lru_cache(maxsize=1)
def _get_search() -> TavilySearch:
    """懒加载 TavilySearch。

    参考实现是在模块导入时就创建 TavilySearch，但那会立刻校验 API key，
    导致没有密钥时连 import 都失败。改成按需创建后：导入不要求密钥，
    只有真正发起搜索时才需要——更方便测试，也更符合「用到才初始化」的习惯。
    """
    kwargs = {"max_results": settings.search_max_results}
    if settings.tavily_api_key:
        kwargs["tavily_api_key"] = settings.tavily_api_key
    return TavilySearch(**kwargs)


def _has_error(result) -> bool:
    if isinstance(result, dict):
        return bool(result.get("error"))
    text = str(result).lower()
    return any(
        marker in text
        for marker in ("error 432", "usage limit", "rate limit", "quota")
    )


def _duckduckgo_search(query: str) -> dict:
    """免费降级搜索，统一成 Tavily 风格的 results 结构。"""
    try:
        raw = DDGS().text(query, max_results=settings.search_max_results)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"DuckDuckGo: {type(exc).__name__}: {exc}"}

    results: list[dict] = []
    for item in raw or []:
        url = str(item.get("href") or item.get("url") or "")
        if not url:
            continue
        results.append(
            {
                "url": url,
                "title": str(item.get("title") or ""),
                "content": str(item.get("body") or item.get("content") or ""),
                "score": 0.0,
            }
        )
    return {"query": query, "provider": "duckduckgo", "results": results}


@tool("web_search", description="搜索互联网获取最新信息，用于回答需要外部资料佐证的问题。")
def web_search(query: str) -> str:
    """优先 Tavily；auto 模式下额度/限流失败时自动切 DuckDuckGo。"""
    provider = (settings.search_provider or "auto").lower()
    if provider in {"auto", "tavily"}:
        try:
            result = _get_search().invoke({"query": query})
            if not _has_error(result):
                return result
            if provider == "tavily":
                return result
        except Exception as exc:  # noqa: BLE001
            if provider == "tavily":
                return {"error": f"Tavily: {type(exc).__name__}: {exc}"}
    return _duckduckgo_search(query)
