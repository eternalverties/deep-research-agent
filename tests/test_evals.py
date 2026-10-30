"""M8 的离线测试：数据集、指标聚合与阈值逻辑，不联网。"""

from pathlib import Path

from research_agent.evaluation import (
    JudgeScore,
    citation_accuracy,
    evaluate,
    load_dataset,
    passes_thresholds,
)
from research_agent.state import Finding

DATASET_PATH = Path(__file__).parents[1] / "evals" / "dataset.json"


def test_dataset_is_valid() -> None:
    dataset = load_dataset(DATASET_PATH)
    assert len(dataset) >= 3
    ids = [case["id"] for case in dataset]
    assert len(ids) == len(set(ids))
    for case in dataset:
        assert case["query"]
        assert case["expected_points"]


def test_citation_accuracy_is_one_when_all_supported() -> None:
    report = {"citations": [{"title": "A", "url": "https://a.com"}], "sections": []}
    findings = [Finding(claim="x", source_url="https://a.com")]
    assert citation_accuracy(report, findings) == 1.0


def test_passes_thresholds() -> None:
    assert passes_thresholds({"a": 0.8}, {"a": 0.7}) is True
    assert passes_thresholds({"a": 0.6}, {"a": 0.7}) is False


class StubGraph:
    def invoke(self, inputs, config):
        return {
            "report": {
                "summary": "摘要",
                "sections": [
                    {"heading": "节", "content": "内容", "citations": ["https://a.com"]}
                ],
                "citations": [{"title": "A", "url": "https://a.com"}],
            },
            "findings": [Finding(claim="x", source_url="https://a.com")],
            "verification": {"coverage": 0.75},
        }


class InfraErrorGraph:
    def invoke(self, inputs, config):
        return {"infrastructure_error": "Error 432: usage limit exceeded"}


def test_evaluate_aggregates_scores() -> None:
    result = evaluate(
        StubGraph(),
        [{"id": "case-1", "query": "问题", "expected_points": ["要点"]}],
        faithfulness_fn=lambda q, r, f: JudgeScore(score=0.9, reason="ok"),
        coverage_fn=lambda q, e, r: JudgeScore(score=0.8, reason="ok"),
        citation_fn=lambda report, findings: 1.0,
    )
    assert result["passed"] is True
    assert result["means"] == {
        "faithfulness": 0.9,
        "coverage": 0.8,
        "citation_accuracy": 1.0,
        "claim_support_rate": 0.75,
    }
    assert result["cases"][0]["id"] == "case-1"


def test_evaluate_marks_infrastructure_error() -> None:
    result = evaluate(
        InfraErrorGraph(),
        [{"id": "case-1", "query": "问题", "expected_points": ["要点"]}],
    )
    assert result["passed"] is False
    assert "检索服务不可用" in result["error"]
    assert result["cases"][0]["infrastructure_error"]
