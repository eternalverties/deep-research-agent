"""Researcher 节点：一个子任务 = 一个 ReAct 子智能体。

对照主蓝本的 nodes/researcher.py：
- 用 create_agent 包一个「模型 + web_search 工具」的 ReAct 循环；
- 用 LLMCallCounter 统计这次子任务真实花掉的模型调用数；
- 返回 findings / llm_calls，交给父图用 reducer 累加。
"""

from __future__ import annotations

import re
from functools import lru_cache

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage

from research_agent.guardrails import LLMCallCounter
from research_agent.models import get_model
from research_agent.state import Finding
from research_agent.tools.search import web_search

_RESEARCHER_SYSTEM = """你是一个研究执行员，只负责一个子任务。
先用 web_search 检索可核实的资料，再基于检索结果给出简洁、事实性的发现。
不要编造来源；如果检索不到证据，就明确说没有找到。"""

# 只匹配 URL 的合法字符，遇到中文/空格/中文标点会自然停止，
# 避免把「https://x.com/y，然后……」这类中文上下文吞进 URL。
_URL_RE = re.compile(r"https?://[A-Za-z0-9\-._~:/?#@!$&*+;=%\[\]]+")


@lru_cache(maxsize=1)
def _get_agent():
    """懒加载 + 缓存，避免每个并行分支重复构建智能体。"""
    return create_agent(
        get_model("researcher"),
        tools=[web_search],
        system_prompt=_RESEARCHER_SYSTEM,
    )


def _as_text(content) -> str:
    """把 LangChain 消息内容统一成字符串（兼容多段 content blocks）。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text", "")))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)


def extract_urls(text: str) -> list[str]:
    """从文本中提取并去重 URL，保持出现顺序。"""
    seen: set[str] = set()
    urls: list[str] = []
    for raw in _URL_RE.findall(text):
        url = raw.rstrip(".,;:!?")
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def researcher_node(state: dict) -> dict:
    """执行单个子任务，返回结构化发现与本次模型调用数。"""
    task = state["subtasks"][0]
    counter = LLMCallCounter()
    result = _get_agent().invoke(
        {"messages": [HumanMessage(content=f"研究子任务：{task}")]},
        config={"callbacks": [counter]},
    )
    messages = result["messages"]
    answer = _as_text(messages[-1].content)

    # 工具调用结果和最终回答里都可能出现来源 URL，统一收集。
    haystack = "\n".join(_as_text(m.content) for m in messages)
    # 每个分支最多保留 6 个来源：既保证可溯源，又避免状态和后续上下文无限膨胀。
    urls = extract_urls(haystack)[:6]

    if urls:
        findings = [Finding(claim=answer[:600], source_url=url) for url in urls]
    else:
        findings = [Finding(claim=answer[:600], source_url="")]

    return {"findings": findings, "llm_calls": counter.count}
