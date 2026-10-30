"""评测：LLM-as-judge（忠实度/覆盖度）+ 程序化引用准确率。"""

from __future__ import annotations

import json
import statistics
import uuid
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, Field

from research_agent.config import settings
from research_agent.guardrails import verify_citations
from research_agent.models import get_model
from research_agent.reporting import render_report_markdown


class JudgeScore(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    reason: str = ""


def _field(item, name: str, default: str = ""):
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


_FAITHFULNESS_SYSTEM = """你是严格的事实核查员。
判断【报告】中的事实性断言是否都能由【研究素材】支持。
规则：
1. 不要求报告覆盖全部素材，只检查是否编造、歪曲或超出素材；
2. 1.0 表示所有关键断言都有素材依据；0.0 表示大量断言无依据；
3. 允许合理的总结与归纳，但不得引入素材之外的新事实。
只输出 score 与简短 reason。"""

_COVERAGE_SYSTEM = """你是研究完整性评审员。
按【期望要点】检查【报告】的覆盖程度。
score = 已覆盖的要点数 / 总要点数，允许部分覆盖；只覆盖次要内容也得分。
只输出 score 与简短 reason。"""


def _judge(system: str, human: str) -> JudgeScore:
    judge = get_model("judge").with_structured_output(JudgeScore)
    result = judge.invoke([("system", system), ("human", human)])
    if result is None:
        return JudgeScore(score=0.0, reason="judge 未返回结构化结果")
    return result


def judge_faithfulness(query: str, report_text: str, findings_text: str) -> JudgeScore:
    return _judge(
        _FAITHFULNESS_SYSTEM,
        f"原始问题：{query}\n\n【报告】\n{report_text}\n\n【研究素材】\n{findings_text}",
    )


def judge_coverage(query: str, expected_points: list[str], report_text: str) -> JudgeScore:
    points = "\n".join(f"- {point}" for point in expected_points)
    return _judge(
        _COVERAGE_SYSTEM,
        f"原始问题：{query}\n\n【期望要点】\n{points}\n\n【报告】\n{report_text}",
    )


def citation_accuracy(report: dict, findings) -> float:
    coverage, _ = verify_citations(findings, report)
    return coverage


def load_dataset(path: str | Path) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise TypeError("评测数据集必须是 JSON 数组")
    return data


def passes_thresholds(means: dict, thresholds: dict) -> bool:
    return all(means[key] >= value for key, value in thresholds.items())


def evaluate(
    app,
    dataset: list[dict],
    max_cases: int = 0,
    faithfulness_fn: Callable = judge_faithfulness,
    coverage_fn: Callable = judge_coverage,
    citation_fn: Callable = citation_accuracy,
) -> dict:
    """逐条跑评测，返回每条结果、均值与是否达标。"""
    cases = dataset[:max_cases] if max_cases else dataset
    results: list[dict] = []

    for case in cases:
        result = app.invoke(
            {"query": case["query"]},
            config={
                "configurable": {"thread_id": f"eval-{uuid.uuid4().hex[:8]}"},
                "max_concurrency": 3,
            },
        )
        infrastructure_error = result.get("infrastructure_error")
        if infrastructure_error:
            results.append(
                {
                    "id": case["id"],
                    "infrastructure_error": infrastructure_error,
                    "faithfulness": None,
                    "coverage": None,
                    "citation_accuracy": None,
                    "claim_support_rate": None,
                    "reason": {},
                }
            )
            continue

        report = result.get("report") or {}
        findings = result.get("findings") or []
        evidence = result.get("evidence") or []
        report_text = render_report_markdown(report)
        findings_text = "\n".join(
            f"- {_field(f, 'claim')}（{_field(f, 'source_url')}）"
            for f in findings
        )
        evidence_text = "\n".join(
            f"- {_field(item, 'quote')[:600]}（{_field(item, 'source_url')}）"
            for item in evidence[:30]
        )
        if evidence_text:
            findings_text += "\n\n证据片段：\n" + evidence_text

        faithfulness = faithfulness_fn(case["query"], report_text, findings_text)
        coverage = coverage_fn(case["query"], case["expected_points"], report_text)
        citation = citation_fn(report, findings)
        verification = result.get("verification") or {}
        results.append(
            {
                "id": case["id"],
                "faithfulness": round(faithfulness.score, 3),
                "coverage": round(coverage.score, 3),
                "citation_accuracy": round(citation, 3),
                "claim_support_rate": round(float(verification.get("coverage", 0.0)), 3),
                "reason": {
                    "faithfulness": faithfulness.reason,
                    "coverage": coverage.reason,
                },
            }
        )

    scored = [item for item in results if item.get("faithfulness") is not None]
    errors = [item for item in results if item.get("infrastructure_error")]
    means = {
        "faithfulness": round(statistics.mean(r["faithfulness"] for r in scored), 3)
        if scored
        else 0.0,
        "coverage": round(statistics.mean(r["coverage"] for r in scored), 3)
        if scored
        else 0.0,
        "citation_accuracy": round(
            statistics.mean(r["citation_accuracy"] for r in scored), 3
        )
        if scored
        else 0.0,
        "claim_support_rate": round(
            statistics.mean(r["claim_support_rate"] for r in scored), 3
        )
        if scored
        else 0.0,
    }
    thresholds = {
        "faithfulness": settings.eval_min_faithfulness,
        "coverage": settings.eval_min_coverage,
        "citation_accuracy": settings.eval_min_citation_accuracy,
    }
    result = {
        "passed": bool(scored)
        and not errors
        and passes_thresholds(means, thresholds),
        "means": means,
        "thresholds": thresholds,
        "cases": results,
    }
    if errors:
        result["error"] = "部分用例因检索服务不可用未完成"
    return result
