"""Planner 节点：把用户的研究问题拆成 3–5 个可独立检索的子任务。"""

from pydantic import BaseModel, Field, ValidationError

from research_agent.models import get_model


class ResearchPlan(BaseModel):
    """Planner 的结构化输出。"""

    subtasks: list[str] = Field(
        min_length=3,
        max_length=5,
        description="3–5 个互不重叠、可以独立联网检索的研究子任务",
    )


_PLANNER_SYSTEM = """你是一个严谨的研究规划器。
把用户的研究问题拆解成 3–5 个互不重叠、可以独立联网检索的子任务。
要求：
1. 每个子任务具体、可执行，能直接拿去搜索；
2. 子任务合起来要覆盖原问题，不要重复；
3. 如果提供了「修改意见」或「缺口」，请据此重新规划。
只输出结构化结果，不要输出多余解释。"""


def _feedback_text(state: dict) -> str:
    """把人工反馈和 critic 缺口合并成一段提示文本。"""
    parts: list[str] = []
    if state.get("plan_feedback"):
        parts.append(f"人工修改意见：{state['plan_feedback']}")
    gaps = state.get("gaps") or []
    if gaps:
        parts.append("尚未覆盖的缺口：" + "；".join(gaps))
    return "\n".join(parts) if parts else "无"


def planner_node(state: dict) -> dict:
    """调用模型做结构化拆解，返回状态的部分更新。"""
    try:
        plan: ResearchPlan = get_model("planner").with_structured_output(ResearchPlan).invoke(
            [
                ("system", _PLANNER_SYSTEM),
                ("human", f"研究问题：{state['query']}\n\n修改依据：{_feedback_text(state)}"),
            ]
        )
    except ValidationError:
        # 问题过于笼统时模型可能只返回 1 个子任务；转成可读的拒绝状态，
        # 而不是让整个图因为一次结构化校验失败而崩溃。
        return {
            "rejected": True,
            "rejection_reason": "问题过于笼统，无法拆解成有效的检索子任务，请补充具体范围或背景。",
        }
    return {"subtasks": plan.subtasks, "plan_feedback": "", "llm_calls": 1}
