"""联网搜索工具：Tavily 主提供方 + Bing RSS 免费降级。"""

import re
import threading
import time
import xml.etree.ElementTree as ET
from functools import lru_cache
from html import unescape

import httpx
from langchain.tools import tool
from langchain_tavily import TavilySearch

from research_agent.config import settings

_BING_LOCK = threading.Lock()


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


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()


def _bing_search(query: str) -> dict:
    """Bing RSS 免费降级；httpx 的 timeout 是硬超时。"""
    root = None
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            with _BING_LOCK:
                response = httpx.get(
                    "https://www.bing.com/search",
                    params={"q": query, "format": "rss"},
                    timeout=httpx.Timeout(settings.search_timeout_seconds, connect=5.0),
                    follow_redirects=True,
                    headers={"User-Agent": "Mozilla/5.0"},
                )
            if not response.content:
                raise ValueError("empty Bing response")
            response.raise_for_status()
            root = ET.fromstring(response.content)
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt == 0:
                time.sleep(0.8)
    if root is None:
        return {"error": f"Bing: {type(last_error).__name__}: {last_error}"}

    results: list[dict] = []
    for item in root.findall(".//item")[: settings.search_max_results]:
        url = (item.findtext("link") or "").strip()
        if not url:
            continue
        description = item.find("description")
        description_text = "".join(description.itertext()) if description is not None else ""
        results.append(
            {
                "url": url,
                "title": _clean_text(item.findtext("title") or ""),
                "content": _clean_text(description_text),
                "score": 0.0,
            }
        )
    return {"query": query, "provider": "bing", "results": results}


@tool("web_search", description="搜索互联网获取最新信息，用于回答需要外部资料佐证的问题。")
def web_search(query: str) -> str:
    """优先 Tavily；auto 模式下额度/限流失败时自动切 Bing。"""
    provider = (settings.search_provider or "auto").lower()
    if provider == "duckduckgo":  # 兼容旧配置
        provider = "bing"
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
    return _bing_search(query)
