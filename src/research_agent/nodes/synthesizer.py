"""Synthesizer 节点：把零散发现综合成结构化、可溯源的报告。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from research_agent.models import get_model


class Citation(BaseModel):
    title: str
    url: str


class ReportSection(BaseModel):
    heading: str
    content: str
    citations: list[str] = Field(default_factory=list, description="本节引用到的 URL")


class ResearchReport(BaseModel):
    """Synthesizer 的结构化输出。"""

    summary: str
    sections: list[ReportSection]
    citations: list[Citation]


_SYNTH_SYSTEM = """你是研究报告综合员。基于给定「研究发现」写一份严谨的结构化报告。
要求：
1. summary 用 3–5 句话直接回答原问题；
2. sections 写 3–5 节，每节有清晰小标题，内容必须来自已有发现；
3. citations 只能从「可用来源清单」里选，绝对不能编造 URL；
4. 每节的 citations 列出本节实际用到的 URL；
5. 如果给出「修复要求」，必须按它修正；
6. 证据不足的地方要明确写出局限，不要用常识补齐。
只输出结构化结果。"""


def _group_findings(findings, max_items: int = 12, max_chars: int = 300) -> str:
    grouped: dict[str, list[str]] = {}
    for item in findings or []:
        claim = item.claim if not isinstance(item, dict) else item.get("claim", "")
        url = item.source_url if not isinstance(item, dict) else item.get("source_url", "")
        grouped.setdefault(claim, [])
        if url and url not in grouped[claim]:
            grouped[claim].append(url)
    lines: list[str] = []
    for claim, urls in list(grouped.items())[:max_items]:
        lines.append(f"- {claim[:max_chars]}")
        if urls:
            lines.append("  来源：" + "；".join(urls))
    return "\n".join(lines) if lines else "（暂无发现）"


def _source_catalog(findings, max_urls: int = 20) -> str:
    urls: list[str] = []
    for item in findings or []:
        url = item.source_url if not isinstance(item, dict) else item.get("source_url", "")
        if url and url not in urls:
            urls.append(url)
    selected = urls[:max_urls]
    return "\n".join(f"- {url}" for url in selected) if selected else "（无可用来源）"


def _fallback_report(findings) -> dict:
    """结构化输出失败时的保底报告：把已有发现整理成分节 + 来源。"""
    grouped: dict[str, list[str]] = {}
    for item in findings or []:
        claim = item.claim if not isinstance(item, dict) else item.get("claim", "")
        url = item.source_url if not isinstance(item, dict) else item.get("source_url", "")
        urls = grouped.setdefault(claim, [])
        if url and url not in urls:
            urls.append(url)

    sections = []
    citations = []
    seen: set[str] = set()
    for i, (claim, urls) in enumerate(grouped.items(), 1):
        sections.append(
            {"heading": f"发现 {i}", "content": claim, "citations": urls[:3]}
        )
        for url in urls:
            if url and url not in seen:
                seen.add(url)
                citations.append({"title": url, "url": url})

    if not sections:
        sections = [{"heading": "说明", "content": "本次运行没有获得可用发现。", "citations": []}]
    return {
        "summary": "（结构化报告生成失败，已启用回退摘要）请结合下方分节阅读已有发现。",
        "sections": sections,
        "citations": citations,
    }


def synthesizer_node(state: dict) -> dict:
    """生成（或在修复时重写）结构化报告。"""
    findings = state.get("findings") or []
    repair_notes = state.get("repair_notes") or "无"

    messages = [
        ("system", _SYNTH_SYSTEM),
        (
            "human",
            f"原始问题：{state['query']}\n\n"
            f"研究发现：\n{_group_findings(findings)}\n\n"
            f"可用来源清单（只能引用这些 URL）：\n{_source_catalog(findings)}\n\n"
            f"修复要求：{repair_notes}",
        ),
    ]
    structured = get_model("synthesizer").with_structured_output(ResearchReport)

    # DeepSeek 偶尔会返回普通文本而不发起工具调用，此时结构化结果会是 None。
    # 重试一次通常能恢复；仍失败才使用回退报告。
    report = None
    calls = 0
    for _ in range(2):
        report = structured.invoke(messages)
        calls += 1
        if report is not None:
            break

    # DeepSeek 偶尔会返回空的工具调用；此时不能直接崩溃，改用回退报告，
    # 保证已经花掉的研究成本仍然能产出可审计的结果。
    data = report.model_dump() if report is not None else _fallback_report(findings)
    return {
        "report": data,
        "citations": [citation["url"] for citation in data["citations"]],
        "llm_calls": calls,
    }
