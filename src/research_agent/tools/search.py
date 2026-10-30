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
_TAVILY_DISABLED = False


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


def _serper_search(query: str) -> dict:
    """Serper（Google 结果）降级；需要 SERPER_API_KEY。"""
    if not settings.serper_api_key:
        return {"error": "Serper: API key not configured"}
    try:
        response = httpx.post(
            "https://google.serper.dev/search",
            headers={
                "X-API-KEY": settings.serper_api_key,
                "Content-Type": "application/json",
            },
            json={"q": query, "num": settings.search_max_results},
            timeout=httpx.Timeout(settings.search_timeout_seconds, connect=5.0),
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Serper: {type(exc).__name__}: {exc}"}

    results: list[dict] = []
    for item in (data.get("organic") or [])[: settings.search_max_results]:
        url = str(item.get("link") or "")
        if not url or "google.com/goto" in url or "google.com/url?" in url:
            continue
        results.append(
            {
                "url": url,
                "title": _clean_text(item.get("title") or ""),
                "content": _clean_text(item.get("snippet") or ""),
                "score": 0.0,
            }
        )
    return {"query": query, "provider": "serper", "results": results}


@tool("web_search", description="搜索互联网获取最新信息，用于回答需要外部资料佐证的问题。")
def web_search(query: str) -> str:
    """auto 模式：Tavily -> Serper -> Bing RSS。"""
    global _TAVILY_DISABLED
    provider = (settings.search_provider or "auto").lower()
    if provider == "duckduckgo":  # 兼容旧配置
        provider = "bing"
    if provider == "serper":
        return _serper_search(query)
    if provider == "bing":
        return _bing_search(query)
    if provider == "tavily":
        try:
            return _get_search().invoke({"query": query})
        except Exception as exc:  # noqa: BLE001
            return {"error": f"Tavily: {type(exc).__name__}: {exc}"}

    # auto：Tavily 失败一次后熔断，本次进程后续直接走 Serper/Bing。
    if not _TAVILY_DISABLED:
        try:
            result = _get_search().invoke({"query": query})
            if not _has_error(result):
                return result
            _TAVILY_DISABLED = True
        except Exception:  # noqa: BLE001
            _TAVILY_DISABLED = True
    if settings.serper_api_key:
        result = _serper_search(query)
        if not _has_error(result):
            return result
    return _bing_search(query)
