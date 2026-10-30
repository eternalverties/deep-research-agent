"""Critic 节点：评估已有发现是否覆盖原问题，不够就指出缺口。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from research_agent.models import get_model


class CriticVerdict(BaseModel):
    """Critic 的结构化输出。"""

    sufficient: bool = Field(description="现有发现是否已经覆盖原问题的主要方面")
    gaps: list[str] = Field(default_factory=list, description="尚未覆盖或证据不足的具体缺口")
    notes: str = Field(default="", description="一句话总体评价")


_CRITIC_SYSTEM = """你是严谨的研究质量评审员。
根据原始问题和已有发现，判断当前研究的覆盖是否充分。
规则：
1. 只要存在会影响结论的重要缺口，就判定 sufficient=false；
2. gaps 要具体、可操作，能直接交给规划器生成新的检索子任务；
3. 如果主要方面都已覆盖，判定 sufficient=true 并返回空 gaps；
4. 不要因为措辞不同就判为缺口。
只输出结构化结果。"""


def _findings_digest(findings, limit: int = 20) -> str:
    """把发现压缩成给评审员看的摘要，控制 prompt 体积。"""
    lines: list[str] = []
    for item in findings[:limit]:
        source = item.source_url or "无来源"
        lines.append(f"- {item.claim[:200]}（来源：{source}）")
    return "\n".join(lines) if lines else "（暂无发现）"


def critic_node(state: dict) -> dict:
    """评估覆盖度，并累加迭代次数与本次模型调用。"""
    subtasks = "\n".join(f"- {task}" for task in state.get("subtasks", [])) or "（无）"
    # 同一条研究结论可能对应多个来源，digest 里按 claim 去重后再给评审员看。
    unique_findings = []
    seen_claims: set[str] = set()
    for item in state.get("findings") or []:
        if item.claim not in seen_claims:
            seen_claims.add(item.claim)
            unique_findings.append(item)

    verdict: CriticVerdict = get_model("critic").with_structured_output(CriticVerdict).invoke(
        [
            ("system", _CRITIC_SYSTEM),
            (
                "human",
                f"原始问题：{state['query']}\n\n"
                f"已拆解的子任务：\n{subtasks}\n\n"
                f"已有发现：\n{_findings_digest(unique_findings)}",
            ),
        ]
    )

    return {
        "iterations": state.get("iterations", 0) + 1,
        "_sufficient": verdict.sufficient,
        "gaps": verdict.gaps,
        "llm_calls": 1,
    }
