"""Claim-Evidence 核验的离线测试。"""

import json

from langchain_core.messages import ToolMessage

from research_agent.nodes.researcher import _extract_evidence, _tool_errors
from research_agent.nodes.verifier import (
    _fallback_claims,
    candidate_evidence,
    summarize_claims,
)
from research_agent.state import Claim, Evidence


def _evidence(evidence_id: str, url: str, quote: str) -> Evidence:
    return Evidence(evidence_id=evidence_id, source_url=url, quote=quote)


def test_candidate_evidence_prefers_cited_urls() -> None:
    claim = Claim(claim_id="c1", content="远程办公降低跨组协作", cited_urls=["https://a.com"])
    direct = _evidence("ev-a", "https://a.com", "跨组协作下降")
    other = _evidence("ev-b", "https://b.com", "完全无关")
    result = candidate_evidence(claim, [other, direct], 5)
    assert result[0].source_url == "https://a.com"


def test_candidate_evidence_falls_back_to_all() -> None:
    claim = Claim(claim_id="c1", content="远程办公", cited_urls=[])
    item = _evidence("ev-a", "https://a.com", "远程办公的实证研究")
    assert candidate_evidence(claim, [item], 5) == [item]


def test_summarize_claims() -> None:
    claims = [
        Claim(claim_id="c1", content="A", status="supported"),
        Claim(claim_id="c2", content="B", status="insufficient"),
    ]
    summary = summarize_claims(claims)
    assert summary == {
        "supported": 1,
        "contradicted": 0,
        "insufficient": 1,
        "total": 2,
        "coverage": 0.5,
    }


def test_extract_evidence_from_tool_message() -> None:
    payload = {
        "results": [
            {
                "url": "https://a.com",
                "title": "A",
                "content": "一段可引用的证据正文",
                "score": 0.9,
            }
        ]
    }
    messages = [
        ToolMessage(content=json.dumps(payload, ensure_ascii=False), tool_call_id="tool-1")
    ]
    evidence = _extract_evidence(messages)
    assert len(evidence) == 1
    assert evidence[0].source_url == "https://a.com"
    assert "可引用" in evidence[0].quote


def test_fallback_claims_use_first_sentence() -> None:
    report = {
        "sections": [
            {
                "heading": "节",
                "content": "第一句是事实。第二句也是事实。",
                "citations": ["https://a.com"],
            }
        ]
    }
    drafts = _fallback_claims(report, 5)
    assert drafts[0].content == "第一句是事实。"
    assert drafts[0].cited_urls == ["https://a.com"]


def test_tool_errors_detects_quota_limit() -> None:
    message = ToolMessage(
        content="{'error': ValueError(\"Error 432: usage limit exceeded\")}",
        tool_call_id="tool-error",
    )
    errors = _tool_errors([message])
    assert errors
    assert "432" in errors[0]
