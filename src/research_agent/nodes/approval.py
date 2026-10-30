"""人在回路审批闸门：在昂贵的并行研究开始前让操作者确认计划。"""

from __future__ import annotations

from langgraph.types import interrupt

from research_agent.config import settings


def approval_node(state: dict) -> dict:
    """审批第一版计划；后续 critic 回流不重复打扰人工。"""
    # HITL 关闭，或已经在 critic 回流后的重规划 → 直接放行。
    if not settings.hitl_approval_enabled or state.get("iterations", 0) > 0:
        return {"_plan_rejected": False}

    decision = interrupt(
        {
            "type": "plan_approval",
            "message": "请审批研究计划：approve / edit / reject / abort",
            "query": state.get("query"),
            "proposed_subtasks": state.get("subtasks", []),
        }
    )

    action = (decision or {}).get("action", "approve")
    if action == "edit":
        return {
            "subtasks": decision.get("subtasks", []),
            "_plan_rejected": False,
            "plan_feedback": "",
        }
    if action == "reject":
        return {
            "_plan_rejected": True,
            "plan_feedback": decision.get("feedback", ""),
        }
    if action == "abort":
        reason = decision.get("reason") or "用户中止了本次研究。"
        return {
            "_aborted": True,
            "report": {
                "summary": f"研究已中止：{reason}",
                "sections": [],
                "citations": [],
            },
        }
    return {"_plan_rejected": False, "plan_feedback": ""}
