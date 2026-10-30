"""健壮性与成本计数。

- LLMCallCounter：统计一次 invoke 内部真实发生的模型调用次数。
- RETRY_POLICY：LangGraph 节点级重试策略，遇到瞬时网络/限流错误指数退避。
"""

import re
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


# ── 输出护栏：引用真实性 ───────────────────────────────────────────────
def _finding_url(finding) -> str:
    if isinstance(finding, dict):
        return finding.get("source_url", "") or ""
    return getattr(finding, "source_url", "") or ""


def _report_urls(report: dict) -> list[str]:
    """收集报告顶层与各分节声明的 URL（去重，保持顺序）。"""
    urls: list[str] = []
    seen: set[str] = set()
    for citation in (report or {}).get("citations", []) or []:
        if isinstance(citation, dict):
            url = citation.get("url", "") or ""
        else:
            url = str(citation)
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    for section in (report or {}).get("sections", []) or []:
        if isinstance(section, dict):
            for raw in section.get("citations", []) or []:
                url = str(raw)
                if url and url not in seen:
                    seen.add(url)
                    urls.append(url)
    return urls


def verify_citations(findings, report: dict) -> tuple[float, list[str]]:
    """硬性引用校验：报告中每个 URL 都必须出现在检索得到的来源里。

    返回 (覆盖率, 无法溯源的 URL 列表)。没有引用时覆盖率为 0——一份
    没有来源的报告不应通过校验。
    """
    cited = _report_urls(report)
    if not cited:
        return 0.0, []
    allowed = {_finding_url(item) for item in (findings or [])}
    unsupported = [url for url in cited if url not in allowed]
    coverage = (len(cited) - len(unsupported)) / len(cited)
    return coverage, unsupported


# ── 输出护栏：内容检查 ────────────────────────────────────────────────
_PROMPT_LEAK_MARKERS = (
    "system prompt",
    "you are a strict evaluator",
    "as an ai language model",
    "以下是系统提示",
)
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_LONG_DIGITS_RE = re.compile(r"\b(?:\d[ -]?){9,}\b")


def scan_content(text: str) -> list[str]:
    """检查提示词泄漏与可能的 PII（邮箱、手机号/卡号形态）。"""
    flags: list[str] = []
    text = text or ""
    low = text.lower()
    for marker in _PROMPT_LEAK_MARKERS:
        if marker in low:
            flags.append(f"疑似提示词泄漏：'{marker}'")

    # URL 里的 DOI、文章编号常包含长数字串，先剥离 URL 再做 PII 检查，避免误报。
    text_without_urls = re.sub(r"https?://\S+", " ", text)
    if _EMAIL_RE.search(text_without_urls):
        flags.append("疑似 PII：报告中出现邮箱地址")
    if _LONG_DIGITS_RE.search(text_without_urls):
        flags.append("疑似 PII：报告中出现长数字串")
    return flags
