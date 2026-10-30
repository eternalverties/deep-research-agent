"""Researcher 节点：一个子任务 = 一个 ReAct 子智能体。

对照主蓝本的 nodes/researcher.py：
- 用 create_agent 包一个「模型 + web_search 工具」的 ReAct 循环；
- 用 LLMCallCounter 统计这次子任务真实花掉的模型调用数；
- 返回 findings / llm_calls，交给父图用 reducer 累加。
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from functools import lru_cache

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, ToolMessage

from research_agent.guardrails import LLMCallCounter
from research_agent.models import get_model
from research_agent.state import Evidence, Finding
from research_agent.tools.search import web_search

_RESEARCHER_SYSTEM = """你是一个研究执行员，只负责一个子任务。
先用 web_search 检索可核实的资料，再基于检索结果给出简洁、事实性的发现。
不要编造来源；如果检索不到证据，就明确说没有找到。"""

# 只匹配 URL 的合法字符，遇到中文/空格/中文标点会自然停止，
# 避免把「https://x.com/y，然后……」这类中文上下文吞进 URL。
_URL_RE = re.compile(r"https?://[A-Za-z0-9\-._~:/?#@!$&*+;=%\[\]]+")
_INFRA_ERROR_RE = re.compile(
    r"(Error\s*(?:429|432|5\d\d)[^\"'\n}]*|(?:usage|rate)\s*limit[^\"'\n}]*|quota[^\"'\n}]*)",
    re.IGNORECASE,
)


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


def _tool_results(messages) -> list[dict]:
    """把 ToolMessage 里的 Tavily JSON 解析成 result 列表。"""
    results: list[dict] = []
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        text = _as_text(message.content)
        data = None
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            try:
                data = ast.literal_eval(text)
            except (ValueError, SyntaxError):
                continue
        if isinstance(data, dict):
            data = data.get("results") or []
        if isinstance(data, list):
            results.extend(item for item in data if isinstance(item, dict))
    return results


def _evidence_id(url: str, quote: str) -> str:
    return "ev-" + hashlib.sha1(f"{url}\n{quote}".encode()).hexdigest()[:12]


def _extract_evidence(messages) -> list[Evidence]:
    """从工具返回的搜索结果里抽取证据片段，按 URL+正文去重。"""
    evidence: list[Evidence] = []
    seen: set[str] = set()
    for item in _tool_results(messages):
        url = str(item.get("url") or "").strip()
        quote = str(item.get("content") or "").strip()
        if not url or not quote:
            continue
        evidence_id = _evidence_id(url, quote)
        if evidence_id in seen:
            continue
        seen.add(evidence_id)
        evidence.append(
            Evidence(
                evidence_id=evidence_id,
                source_url=url,
                source_title=str(item.get("title") or ""),
                quote=quote[:600],
                score=float(item.get("score") or 0.0),
            )
        )
    return evidence[:12]


def _tool_errors(messages) -> list[str]:
    """识别搜索工具返回的额度/限流/服务端错误。"""
    errors: list[str] = []
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        text = _as_text(message.content)
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            data = None
        if isinstance(data, dict) and data.get("error"):
            errors.append(str(data["error"]))
        errors.extend(match.group(0).strip() for match in _INFRA_ERROR_RE.finditer(text))
    return errors


def _tool_provider(messages) -> str:
    """识别本次检索使用的是 Tavily 还是免费降级后端。"""
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        try:
            data = json.loads(_as_text(message.content))
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict) and data.get("provider"):
            return str(data["provider"])
    return "tavily"


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
    errors = _tool_errors(messages)
    if errors:
        return {
            "findings": [],
            "evidence": [],
            "llm_calls": counter.count,
            "infrastructure_error": errors[0][:300],
            "search_provider": _tool_provider(messages),
        }

    # 工具调用结果和最终回答里都可能出现来源 URL，统一收集。
    haystack = "\n".join(_as_text(m.content) for m in messages)
    # 每个分支最多保留 6 个来源：既保证可溯源，又避免状态和后续上下文无限膨胀。
    urls = extract_urls(haystack)[:6]

    if urls:
        findings = [Finding(claim=answer[:600], source_url=url) for url in urls]
    else:
        findings = [Finding(claim=answer[:600], source_url="")]

    return {
        "findings": findings,
        "evidence": _extract_evidence(messages),
        "llm_calls": counter.count,
        "search_provider": _tool_provider(messages),
    }
