"""联网搜索工具（Tavily）。"""

from functools import lru_cache

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
    kwargs = {"max_results": 4}
    if settings.tavily_api_key:
        kwargs["tavily_api_key"] = settings.tavily_api_key
    return TavilySearch(**kwargs)


@tool("web_search", description="搜索互联网获取最新信息，用于回答需要外部资料佐证的问题。")
def web_search(query: str) -> str:
    """调用 Tavily 搜索，返回整理好的文本结果（含来源 URL）。"""
    return _get_search().invoke({"query": query})
