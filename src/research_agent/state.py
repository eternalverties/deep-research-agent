"""图的共享状态契约。

对照参考实现：用 TypedDict 定义一个贯穿所有节点的状态对象；其中
`findings` 和 `llm_calls` 用 `Annotated[..., add]` 作为 reducer——
当多个并行节点在同一超步里写这两个字段时，LangGraph 会把它们「累加」，
而不是让后写的覆盖先写的。这是并行 fan-out 不丢数据的关键。
"""

from __future__ import annotations

from operator import add
from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel


class Finding(BaseModel):
    """一条可溯源的研究发现。"""

    claim: str
    source_url: str
    source_title: str = ""


class Evidence(BaseModel):
    """一条可引用的证据片段（来自搜索结果正文）。"""

    evidence_id: str
    source_url: str
    source_title: str = ""
    quote: str = ""
    score: float = 0.0


class Claim(BaseModel):
    """报告中的一条原子事实陈述及其核验结果。"""

    claim_id: str
    content: str
    cited_urls: list[str] = []
    status: Literal["supported", "contradicted", "insufficient"] = "insufficient"
    confidence: float = 0.0
    evidence_ids: list[str] = []
    reason: str = ""


def keep_first(left: str | None, right: str | None) -> str:
    """多个并行分支同时报告基础设施错误时，保留第一个非空值。"""
    return left or right or ""


class ResearchState(TypedDict, total=False):
    query: str
    subtasks: list[str]
    findings: Annotated[list[Finding], add]
    evidence: Annotated[list[Evidence], add]
    claims: list[Claim]
    verification: dict
    trace: Annotated[list[dict], add]
    search_provider: Annotated[str, keep_first]
    report: dict
    citations: list[str]
    iterations: int
    gaps: list[str]

    # 护栏与预算
    rejected: bool
    rejection_reason: str
    infrastructure_error: Annotated[str, keep_first]
    llm_calls: Annotated[int, add]
    repairs: int
    repair_notes: str
    guardrail_flags: list[str]

    # 人在回路 / 瞬态路由标记
    plan_feedback: str
    _plan_rejected: bool
    _aborted: bool
    _sufficient: bool
    _needs_repair: bool
