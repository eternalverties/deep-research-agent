"""结构化报告的渲染工具。"""

from __future__ import annotations


def render_report_markdown(report: dict) -> str:
    """把 summary / sections / citations 渲染成可读的 Markdown。"""
    report = report or {}
    lines: list[str] = ["# 研究报告", "", "## 摘要", report.get("summary", ""), ""]

    for section in report.get("sections", []) or []:
        heading = section.get("heading", "未命名章节")
        lines.extend([f"## {heading}", section.get("content", ""), ""])

    citations = report.get("citations", []) or []
    if citations:
        lines.extend(["## 参考来源", ""])
        for citation in citations:
            if isinstance(citation, dict):
                title = citation.get("title", "") or citation.get("url", "")
                url = citation.get("url", "")
                lines.append(f"- [{title}]({url})")
            else:
                lines.append(f"- {citation}")

    return "\n".join(lines).strip() + "\n"
