"""健壮性与成本计数。

- LLMCallCounter：统计一次 invoke 内部真实发生的模型调用次数。
- RETRY_POLICY：LangGraph 节点级重试策略，遇到瞬时网络/限流错误指数退避。
"""

import ssl

from langchain_core.callbacks import BaseCallbackHandler
from langgraph.types import RetryPolicy

from research_agent.config import settings


class LLMCallCounter(BaseCallbackHandler):
    """统计一次 invoke 内部发生了多少次模型调用。

    研究员的 ReAct 循环里，模型调用次数取决于它要检索几轮，事先并不知道；
    用回调计数器就能拿到真实次数，再交给 budget reducer 汇总。
    """

    def __init__(self) -> None:
        self.count = 0

    def on_llm_start(self, *args, **kwargs) -> None:
        self.count += 1

    def on_chat_model_start(self, *args, **kwargs) -> None:
        self.count += 1


def _is_transient(exc: Exception) -> bool:
    """只重试瞬时错误；确定性 bug（ValueError 等）不重试，避免浪费额度。"""
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status is None:
        status = getattr(exc, "status_code", None)
    if status in (429, 500, 502, 503, 504):
        return True
    if isinstance(exc, (ConnectionError, TimeoutError, ssl.SSLError)):
        return True

    name = type(exc).__name__.lower()
    text = str(exc).lower()
    markers = (
        "connect",
        "timeout",
        "ratelimit",
        "ssl",
        "eof",
        "reset",
        "broken pipe",
        "temporarily",
        "unavailable",
    )
    return any(marker in name or marker in text for marker in markers)


RETRY_POLICY = RetryPolicy(
    max_attempts=settings.retry_max_attempts,
    initial_interval=settings.retry_initial_interval,
    backoff_factor=settings.retry_backoff_factor,
    retry_on=_is_transient,
)
