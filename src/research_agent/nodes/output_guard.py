"""输出护栏节点：校验引用真实性、提示词泄漏与 PII。"""

from __future__ import annotations

from research_agent.config import settings
from research_agent.guardrails import scan_content, verify_citations
from research_agent.reporting import render_report_markdown


def output_guard_node(state: dict) -> dict:
    """不合格时给出修复要求；达到修复次数上限则带标记放行。"""
    if not settings.guardrail_output_enabled:
        return {"_needs_repair": False, "guardrail_flags": []}

    report = state.get("report") or {}
    findings = state.get("findings") or []
    coverage, unsupported = verify_citations(findings, report)
    flags: list[str] = []

    if unsupported:
        flags.append(f"有 {len(unsupported)} 条引用不在检索结果中")
    if coverage < settings.min_citation_coverage:
        flags.append(
            f"引用覆盖率 {coverage:.0%} 低于阈值 {settings.min_citation_coverage:.0%}"
        )
    flags.extend(scan_content(render_report_markdown(report)))

    repairs = state.get("repairs", 0)
    if flags and repairs < settings.max_output_repairs:
        notes = "\n".join(flags) + "\n请只引用「可用来源清单」中的 URL，并修正上述问题。"
        return {
            "_needs_repair": True,
            "repair_notes": notes,
            "repairs": repairs + 1,
            "guardrail_flags": flags,
        }

    return {"_needs_repair": False, "guardrail_flags": flags}
