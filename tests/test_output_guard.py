"""M5 的 CI 安全测试：引用校验、内容扫描、报告渲染与修复路由，不联网。"""

from langgraph.graph import END

from research_agent.config import settings
from research_agent.graph import route_after_output_guard
from research_agent.guardrails import scan_content, verify_citations
from research_agent.nodes.output_guard import output_guard_node
from research_agent.nodes.synthesizer import (
    ResearchReport,
    _fallback_report,
    _parse_markdown_report,
)
from research_agent.reporting import render_report_markdown
from research_agent.state import Claim, Finding


def _report(urls: list[str]) -> dict:
    return {
        "summary": "摘要",
        "sections": [{"heading": "第一节", "content": "内容", "citations": urls[:1]}],
        "citations": [{"title": "来源", "url": url} for url in urls],
    }


def test_verify_citations_all_supported() -> None:
    findings = [Finding(claim="x", source_url="https://a.com")]
    coverage, unsupported = verify_citations(findings, _report(["https://a.com"]))
    assert coverage == 1.0
    assert unsupported == []


def test_verify_citations_detects_fabricated_url() -> None:
    findings = [Finding(claim="x", source_url="https://a.com")]
    coverage, unsupported = verify_citations(
        findings, _report(["https://a.com", "https://fake.com"])
    )
    assert coverage == 0.5
    assert unsupported == ["https://fake.com"]


def test_verify_citations_without_citations_scores_zero() -> None:
    coverage, unsupported = verify_citations([], {"sections": [], "citations": []})
    assert coverage == 0.0
    assert unsupported == []


def test_scan_content_flags_pii_and_prompt_leak() -> None:
    flags = scan_content("请联系 test@example.com。这里出现了 system prompt。")
    assert any("PII" in flag for flag in flags)
    assert any("提示词" in flag for flag in flags)


def test_scan_content_ignores_digits_inside_urls() -> None:
    markdown = "- [Nature](https://www.nature.com/articles/s41562-021-01196-4)"
    flags = scan_content(markdown)
    assert not any("长数字串" in flag for flag in flags)


def test_render_report_markdown() -> None:
    markdown = render_report_markdown(_report(["https://a.com"]))
    assert "# 研究报告" in markdown
    assert "## 摘要" in markdown
    assert "## 第一节" in markdown
    assert "## 参考来源" in markdown


def test_route_after_output_guard() -> None:
    assert route_after_output_guard({"_needs_repair": True}) == "synthesizer"
    assert route_after_output_guard({"_needs_repair": False}) == END


def test_output_guard_requests_repair_for_bad_citation() -> None:
    state = {
        "report": _report(["https://fake.com"]),
        "findings": [Finding(claim="x", source_url="https://a.com")],
        "repairs": 0,
    }
    result = output_guard_node(state)
    assert result["_needs_repair"] is True
    assert result["repairs"] == 1
    assert result["guardrail_flags"]


def test_output_guard_ships_with_flags_after_max_repairs() -> None:
    state = {
        "report": _report(["https://fake.com"]),
        "findings": [Finding(claim="x", source_url="https://a.com")],
        "repairs": settings.max_output_repairs,
    }
    result = output_guard_node(state)
    assert result["_needs_repair"] is False
    assert result["guardrail_flags"]


def test_output_guard_flags_contradicted_claim() -> None:
    state = {
        "report": _report(["https://a.com"]),
        "findings": [Finding(claim="x", source_url="https://a.com")],
        "verification": {
            "supported": 0,
            "contradicted": 1,
            "insufficient": 0,
            "total": 1,
        },
        "claims": [
            Claim(
                claim_id="c1",
                content="一个与证据矛盾的断言",
                status="contradicted",
                reason="证据明确相反",
            )
        ],
        "repairs": 0,
    }
    result = output_guard_node(state)
    assert result["_needs_repair"] is True
    assert "矛盾断言" in result["repair_notes"]
    assert "一个与证据矛盾的断言" in result["repair_notes"]


def test_output_guard_skips_repair_when_budget_exhausted() -> None:
    state = {
        "report": _report(["https://fake.com"]),
        "findings": [Finding(claim="x", source_url="https://a.com")],
        "repairs": 0,
        "llm_calls": settings.max_llm_calls_per_run,
    }
    result = output_guard_node(state)
    assert result["_needs_repair"] is False
    assert any("预算不足" in flag for flag in result["guardrail_flags"])


def test_research_report_schema() -> None:
    report = ResearchReport(
        summary="摘要",
        sections=[{"heading": "节", "content": "内容", "citations": ["https://a.com"]}],
        citations=[{"title": "A", "url": "https://a.com"}],
    )
    assert report.citations[0].url == "https://a.com"


def test_fallback_report_uses_findings() -> None:
    report = _fallback_report([Finding(claim="一个发现", source_url="https://a.com")])
    assert report["sections"][0]["content"] == "一个发现"
    assert report["citations"] == [{"title": "https://a.com", "url": "https://a.com"}]


def test_parse_markdown_report() -> None:
    markdown = (
        "## 摘要\n这是摘要。\n\n"
        "## 一、第一节\n内容 [A](https://a.com)。\n\n"
        "## 参考来源\n- [A](https://a.com)"
    )
    report = _parse_markdown_report(markdown)
    assert report["summary"] == "这是摘要。"
    assert report["sections"][0]["heading"] == "一、第一节"
    assert report["citations"] == [{"title": "A", "url": "https://a.com"}]
