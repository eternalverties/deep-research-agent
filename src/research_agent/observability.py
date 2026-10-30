"""轻量级本地可观测性：记录节点耗时、模型调用数与执行摘要。"""

from __future__ import annotations

import time
from functools import wraps


def _detail(node: str, state: dict, result: dict) -> str:
    if node == "input_guard":
        return "拒绝输入" if result.get("rejected") else "输入有效"
    if node == "planner":
        return f"{len(result.get('subtasks') or [])} 个子任务"
    if node == "researcher":
        task = (state.get("subtasks") or ["未知子任务"])[0]
        findings = len(result.get("findings") or [])
        evidence = len(result.get("evidence") or [])
        provider = result.get("search_provider") or "tavily"
        return f"[{provider}] {task[:80]} · 发现 {findings} · 证据 {evidence}"
    if node == "critic":
        verdict = "覆盖充分" if result.get("_sufficient") else "需要补研"
        return f"{verdict} · 缺口 {len(result.get('gaps') or [])}"
    if node == "synthesizer":
        report = result.get("report") or {}
        return (
            f"{len(report.get('sections') or [])} 节 · "
            f"{len(report.get('citations') or [])} 条引用"
        )
    if node == "verifier":
        verification = result.get("verification") or {}
        return (
            f"支持 {verification.get('supported', 0)} · "
            f"矛盾 {verification.get('contradicted', 0)} · "
            f"不足 {verification.get('insufficient', 0)}"
        )
    if node == "output_guard":
        flags = result.get("guardrail_flags") or []
        verdict = "需要修复" if result.get("_needs_repair") else "通过"
        return f"{verdict} · {len(flags)} 个标记"
    if node == "fail":
        return state.get("infrastructure_error") or "检索失败"
    return ""


def traced(node: str):
    """给 LangGraph 节点包一层计时与摘要记录。"""

    def decorator(func):
        @wraps(func)
        def wrapper(state: dict) -> dict:
            started_at = int(time.time() * 1000)
            start = time.perf_counter()
            result = func(state) or {}
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            try:
                calls = int(result.get("llm_calls") or 0)
            except (TypeError, ValueError):
                calls = 0
            event = {
                "node": node,
                "status": "ok",
                "started_at": started_at,
                "duration_ms": duration_ms,
                "iteration": state.get("iterations", 0),
                "llm_calls": calls,
                "detail": _detail(node, state, result),
            }
            return {**result, "trace": [event]}

        return wrapper

    return decorator
