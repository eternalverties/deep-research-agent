"""Claim-Evidence 事实核验：把报告拆成断言，再用检索证据逐条判断。"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from research_agent.config import settings
from research_agent.models import get_model
from research_agent.reporting import render_report_markdown
from research_agent.state import Claim, Evidence


class ClaimDraft(BaseModel):
    content: str
    cited_urls: list[str] = Field(default_factory=list)


class ClaimDrafts(BaseModel):
    claims: list[ClaimDraft] = Field(default_factory=list)


class ClaimVerdict(BaseModel):
    claim_id: str
    status: Literal["supported", "contradicted", "insufficient"]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)
    reason: str = ""


class VerificationResult(BaseModel):
    verdicts: list[ClaimVerdict] = Field(default_factory=list)


_CLAIM_SYSTEM = """你是事实核验流程的第一步：抽取待核验断言。
从报告中抽取 5–8 条原子事实陈述，每条只包含一个可独立核验的事实。
不要抽取建议、观点、方法论或「证据不足」之类的元描述。
为每条保留它所在段落引用的 URL；没有引用就返回空列表。
只输出结构化结果。"""

_VERIFY_SYSTEM = """你是严格的事实核查员。
对每条 CLAIM，只依据给出的 EVIDENCE 片段判断：
- supported：证据直接支持断言的关键事实；
- contradicted：证据明确与断言矛盾；
- insufficient：证据没有覆盖关键事实，或只有间接/模糊关联。
不要用外部常识补充，也不要因为 URL 存在就判定支持。
evidence_ids 只能从该断言对应的 EVIDENCE 中选择；confidence 取 0–1。
只输出结构化结果。"""


def _tokens(text: str) -> set[str]:
    text = (text or "").lower()
    zh = re.findall(r"[\u4e00-\u9fff]", text)
    bigrams = {zh[i] + zh[i + 1] for i in range(len(zh) - 1)}
    words = set(re.findall(r"[a-z0-9]{2,}", text))
    return bigrams | words


def _overlap(claim: str, quote: str) -> float:
    claim_tokens = _tokens(claim)
    quote_tokens = _tokens(quote)
    if not claim_tokens or not quote_tokens:
        return 0.0
    return len(claim_tokens & quote_tokens) / len(claim_tokens)


def candidate_evidence(claim: Claim, evidence: list[Evidence], limit: int) -> list[Evidence]:
    """优先用断言声明的 URL；没有直接引用时按词面重合度排序。"""
    cited = set(claim.cited_urls)
    direct = [item for item in evidence if item.source_url in cited]
    pool = direct if direct else evidence
    ranked = sorted(pool, key=lambda item: _overlap(claim.content, item.quote), reverse=True)
    return ranked[:limit]


def _fallback_claims(report: dict, max_claims: int) -> list[ClaimDraft]:
    """结构化抽取失败时，用每个分节的首句做保底断言。"""
    drafts: list[ClaimDraft] = []
    for section in report.get("sections", []) or []:
        content = (section.get("content") or "").strip()
        if not content:
            continue
        sentence = re.split(r"(?<=[。！？.!?])\s*", content)[0].strip()
        if sentence:
            drafts.append(
                ClaimDraft(
                    content=sentence[:400],
                    cited_urls=list(section.get("citations", []) or [])[:3],
                )
            )
        if len(drafts) >= max_claims:
            break
    return drafts


def extract_claims(report: dict, max_claims: int) -> tuple[list[ClaimDraft], int]:
    """用 LLM 抽取原子断言；失败时回退到分节首句。"""
    text = render_report_markdown(report)
    try:
        result: ClaimDrafts = get_model("verifier").with_structured_output(ClaimDrafts).invoke(
            [("system", _CLAIM_SYSTEM), ("human", f"【报告】\n{text}")]
        )
    except ValidationError:
        result = None
    if result is None or not result.claims:
        return _fallback_claims(report, max_claims), 1
    return result.claims[:max_claims], 1


def verify_claims(
    drafts: list[ClaimDraft], evidence: list[Evidence]
) -> tuple[list[Claim], int, bool]:
    """逐条匹配证据并核验；结构化输出失败时全部标记为证据不足。"""
    claims = [
        Claim(claim_id=f"c{i + 1}", content=draft.content, cited_urls=draft.cited_urls)
        for i, draft in enumerate(drafts)
    ]
    if not claims:
        return [], 0, True

    blocks: list[str] = []
    for claim in claims:
        candidates = candidate_evidence(claim, evidence, settings.verifier_max_evidence)
        blocks.append(f"CLAIM {claim.claim_id}: {claim.content}")
        if not candidates:
            blocks.append("  EVIDENCE: （无）")
        for item in candidates:
            blocks.append(
                f"  EVIDENCE {item.evidence_id} | {item.source_url} | {item.quote[:400]}"
            )

    try:
        result: VerificationResult = get_model("verifier").with_structured_output(
            VerificationResult
        ).invoke(
            [
                ("system", _VERIFY_SYSTEM),
                ("human", "\n".join(blocks)),
            ]
        )
    except ValidationError:
        result = None

    if result is None:
        for claim in claims:
            claim.status = "insufficient"
            claim.reason = "自动核验未返回有效结构化结果"
        return claims, 1, False

    verdicts = {verdict.claim_id: verdict for verdict in result.verdicts}
    for claim in claims:
        verdict = verdicts.get(claim.claim_id)
        if verdict is None:
            claim.status = "insufficient"
            claim.reason = "未返回该断言的核验结果"
            continue
        claim.status = verdict.status
        claim.confidence = verdict.confidence
        claim.evidence_ids = verdict.evidence_ids
        claim.reason = verdict.reason
    return claims, 1, True


def summarize_claims(claims: list[Claim]) -> dict:
    total = len(claims)
    counts = {
        status: sum(1 for claim in claims if claim.status == status)
        for status in ("supported", "contradicted", "insufficient")
    }
    counts["total"] = total
    counts["coverage"] = round(counts["supported"] / total, 3) if total else 0.0
    return counts


def verifier_node(state: dict) -> dict:
    """报告生成后的 Claim-Evidence 核验节点。"""
    if not settings.enable_verifier:
        return {}

    report = state.get("report") or {}
    evidence = state.get("evidence") or []
    drafts, extraction_calls = extract_claims(report, settings.verifier_max_claims)
    claims, verify_calls, ok = verify_claims(drafts, evidence)
    summary = summarize_claims(claims)
    if not ok:
        summary["error"] = "自动核验未返回有效结构化结果"
    return {
        "claims": claims,
        "verification": summary,
        "llm_calls": extraction_calls + verify_calls,
    }
