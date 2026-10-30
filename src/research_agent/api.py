"""FastAPI 服务：把可持久化的研究图暴露成 HTTP 接口。

长任务不能阻塞 HTTP 请求，因此采用「提交-轮询」：
    POST /research                  -> 202 + thread_id（后台线程开始跑）
    GET  /research/{thread_id}      -> running / interrupted / completed / error
    POST /research/{thread_id}/resume -> 提交 HITL 决定，继续暂停的运行
"""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from pydantic import BaseModel, Field

from research_agent.config import settings
from research_agent.graph import build_graph
from research_agent.persistence import sqlite_saver

_STATIC_DIR = Path(__file__).resolve().parent / "static"


class ResearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)


class ResearchAccepted(BaseModel):
    thread_id: str
    status: str = "running"


class ReportSection(BaseModel):
    heading: str
    content: str
    citations: list[str] = Field(default_factory=list)


class Citation(BaseModel):
    title: str
    url: str


class Report(BaseModel):
    summary: str
    sections: list[ReportSection] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)


class ResearchStatus(BaseModel):
    thread_id: str
    status: str
    report: Report | None = None
    guardrail_flags: list[str] = Field(default_factory=list)
    llm_calls: int | None = None
    iterations: int | None = None
    repairs: int | None = None
    verification: dict | None = None
    claims: list[dict] | None = None
    evidence: list[dict] | None = None
    trace: list[dict] | None = None
    search_provider: str | None = None
    infrastructure_error: str | None = None
    error: str | None = None
    interrupt: dict | None = None


class ResumeDecision(BaseModel):
    action: Literal["approve", "edit", "reject", "abort"]
    subtasks: list[str] | None = None
    feedback: str | None = None
    reason: str | None = None


class JobRegistry:
    """进程内状态表；重启后回退到 checkpoint 推断状态。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}

    def start(self, thread_id: str) -> None:
        with self._lock:
            self._jobs[thread_id] = {"status": "running", "error": None, "interrupt": None}

    def finish(self, thread_id: str) -> None:
        with self._lock:
            if thread_id in self._jobs:
                self._jobs[thread_id].update(status="completed", interrupt=None)

    def interrupt(self, thread_id: str, payload: dict) -> None:
        with self._lock:
            if thread_id in self._jobs:
                self._jobs[thread_id].update(status="interrupted", interrupt=payload)

    def fail(self, thread_id: str, error: str) -> None:
        with self._lock:
            if thread_id in self._jobs:
                self._jobs[thread_id].update(status="error", error=error)

    def get(self, thread_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(thread_id)
            return dict(job) if job else None


def _run_config(thread_id: str) -> RunnableConfig:
    return {
        "configurable": {"thread_id": thread_id},
        "run_name": "deep-research",
        "metadata": {
            "model_planner": settings.model_planner,
            "model_researcher": settings.model_researcher,
            "model_synthesizer": settings.model_synthesizer,
            "model_critic": settings.model_critic,
        },
    }


def _run_graph(graph, registry: JobRegistry, thread_id: str, inputs) -> None:
    """后台任务：推进图，并把 running/interrupted/completed/error 写进 registry。"""
    try:
        result = graph.invoke(inputs, config=_run_config(thread_id))
        interrupts = result.get("__interrupt__") if isinstance(result, dict) else None
        if interrupts:
            registry.interrupt(thread_id, interrupts[0].value)
        else:
            registry.finish(thread_id)
    except Exception as exc:  # noqa: BLE001
        registry.fail(thread_id, f"{type(exc).__name__}: {exc}")


def _pending_interrupt(snapshot) -> dict | None:
    for task in getattr(snapshot, "tasks", ()) or ():
        interrupts = getattr(task, "interrupts", ()) or ()
        if interrupts:
            return interrupts[0].value
    return None


def _dump_items(items) -> list[dict]:
    return [item.model_dump() if hasattr(item, "model_dump") else item for item in items or []]


def _read_status(graph, registry: JobRegistry, thread_id: str) -> ResearchStatus:
    snapshot = graph.get_state(_run_config(thread_id))
    values = snapshot.values or {}
    job = registry.get(thread_id)

    if job is not None:
        status, error = job["status"], job["error"]
        interrupt_payload = job.get("interrupt")
    elif values:
        if snapshot.next == () and values.get("report"):
            status, interrupt_payload = "completed", None
        else:
            status, interrupt_payload = "interrupted", _pending_interrupt(snapshot)
        error = None
    else:
        raise HTTPException(status_code=404, detail=f"Unknown thread_id: {thread_id}")

    report = values.get("report")
    completed = status == "completed"
    return ResearchStatus(
        thread_id=thread_id,
        status=status,
        report=Report(**report) if report else None,
        guardrail_flags=values.get("guardrail_flags", []),
        llm_calls=values.get("llm_calls"),
        iterations=values.get("iterations"),
        repairs=values.get("repairs"),
        verification=values.get("verification") if completed else None,
        claims=_dump_items(values.get("claims")) if completed else None,
        evidence=_dump_items(values.get("evidence")) if completed else None,
        trace=values.get("trace"),
        search_provider=values.get("search_provider"),
        infrastructure_error=values.get("infrastructure_error"),
        error=error,
        interrupt=interrupt_payload,
    )


def create_api(graph=None) -> FastAPI:
    """构建 FastAPI app；graph 参数用于测试时注入假图。"""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.registry = JobRegistry()
        app.state.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="research")
        try:
            if graph is not None:
                app.state.graph = graph
                yield
            else:
                with sqlite_saver() as saver:
                    app.state.graph = build_graph(checkpointer=saver)
                    yield
        finally:
            app.state.executor.shutdown(wait=False, cancel_futures=True)

    api = FastAPI(
        title="Deep Research Agent",
        version="0.1.0",
        summary="可持久化、带引用的多智能体研究服务",
        lifespan=lifespan,
    )

    @api.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @api.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(_STATIC_DIR / "index.html")

    @api.post("/research", response_model=ResearchAccepted, status_code=202)
    def start_research(req: ResearchRequest, request: Request) -> ResearchAccepted:
        thread_id = uuid.uuid4().hex
        request.app.state.registry.start(thread_id)
        request.app.state.executor.submit(
            _run_graph,
            request.app.state.graph,
            request.app.state.registry,
            thread_id,
            {"query": req.query},
        )
        return ResearchAccepted(thread_id=thread_id)

    @api.get("/research/{thread_id}", response_model=ResearchStatus)
    def get_research(thread_id: str, request: Request) -> ResearchStatus:
        return _read_status(request.app.state.graph, request.app.state.registry, thread_id)

    @api.post("/research/{thread_id}/resume", response_model=ResearchAccepted, status_code=202)
    def resume_research(
        thread_id: str,
        decision: ResumeDecision,
        request: Request,
    ) -> ResearchAccepted:
        graph, registry = request.app.state.graph, request.app.state.registry
        job = registry.get(thread_id)
        if job is not None:
            if job["status"] != "interrupted":
                raise HTTPException(
                    status_code=409,
                    detail=f"Run is '{job['status']}', not waiting for input.",
                )
        else:
            snapshot = graph.get_state(_run_config(thread_id))
            if not snapshot.values:
                raise HTTPException(status_code=404, detail=f"Unknown thread_id: {thread_id}")
            if snapshot.next == ():
                raise HTTPException(status_code=409, detail="Run is finished, not waiting for input.")

        registry.start(thread_id)
        request.app.state.executor.submit(
            _run_graph,
            graph,
            registry,
            thread_id,
            Command(resume=decision.model_dump(exclude_none=True)),
        )
        return ResearchAccepted(thread_id=thread_id)

    return api


api = create_api()
