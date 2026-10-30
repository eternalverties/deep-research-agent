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

    verification = state.get("verification") or {}
    if verification.get("contradicted"):
        flags.append(f"事实核验发现 {verification['contradicted']} 条矛盾断言")
    if verification.get("insufficient"):
        flags.append(f"事实核验发现 {verification['insufficient']} 条证据不足断言")
    if verification.get("error"):
        flags.append(f"事实核验异常：{verification['error']}")

    claim_notes: list[str] = []
    for claim in state.get("claims") or []:
        status = getattr(claim, "status", None) or (
            claim.get("status", "") if isinstance(claim, dict) else ""
        )
        if status == "supported":
            continue
        content = getattr(claim, "content", None) or (
            claim.get("content", "") if isinstance(claim, dict) else ""
        )
        reason = getattr(claim, "reason", None) or (
            claim.get("reason", "") if isinstance(claim, dict) else ""
        )
        if content:
            claim_notes.append(f"- [{status}] {content[:200]}（{reason[:160]}）")

    repairs = state.get("repairs", 0)
    # 一次修复大约需要 synthesizer 1 次 + verifier 2 次调用。
    can_repair = state.get("llm_calls", 0) + 3 <= settings.max_llm_calls_per_run
    if flags and repairs < settings.max_output_repairs and can_repair:
        notes = "\n".join(flags)
        if claim_notes:
            notes += "\n需要修正的断言：\n" + "\n".join(claim_notes[:8])
        notes += "\n请只引用「可用来源清单」中的 URL，并修正上述问题。"
        return {
            "_needs_repair": True,
            "repair_notes": notes,
            "repairs": repairs + 1,
            "guardrail_flags": flags,
        }

    if flags and repairs < settings.max_output_repairs and not can_repair:
        flags.append("模型调用预算不足，已跳过自动修复")
    return {"_needs_repair": False, "guardrail_flags": flags}
