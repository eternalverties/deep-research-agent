"""输入护栏（M5/M6 会扩展成范围与安全检查；先做最小可用校验）。"""

from __future__ import annotations

_PLACEHOLDERS = {"你的问题", "问题", "test", "测试", "hello", "你好", "..."}
_MIN_CHARS = 6


def input_guard_node(state: dict) -> dict:
    """拦截占位文字、空白和过短输入，避免浪费后面的模型调用。"""
    query = (state.get("query") or "").strip()
    if len(query) < _MIN_CHARS or query.lower() in _PLACEHOLDERS:
        return {
            "rejected": True,
            "rejection_reason": "请输入一个具体的研究问题（至少 6 个字符，不要使用占位文字）。",
        }
    return {"rejected": False, "rejection_reason": ""}
