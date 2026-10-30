"""M7 的 API 测试：用假图验证提交-轮询与 HITL 恢复，不联网。"""

from __future__ import annotations

import time
from types import SimpleNamespace

from fastapi.testclient import TestClient
from langgraph.types import Command

from research_agent.api import create_api

_REPORT = {
    "summary": "测试摘要",
    "sections": [{"heading": "测试节", "content": "测试内容", "citations": ["https://a.com"]}],
    "citations": [{"title": "A", "url": "https://a.com"}],
}


class StubGraph:
    def __init__(self, interrupt_first: bool = False) -> None:
        self.interrupt_first = interrupt_first
        self.values: dict = {}
        self.next: tuple = ()
        self.paused = False

    def invoke(self, inputs, config):
        if isinstance(inputs, Command):
            self.paused = False
            self.next = ()
            self.values = {"report": _REPORT, "llm_calls": 2, "iterations": 1, "repairs": 0}
            return dict(self.values)

        if self.interrupt_first and not self.paused:
            self.paused = True
            self.values = {"query": inputs["query"]}
            self.next = ("approval",)
            return {
                "__interrupt__": [
                    SimpleNamespace(
                        value={
                            "type": "plan_approval",
                            "query": inputs["query"],
                            "proposed_subtasks": ["甲", "乙", "丙"],
                        }
                    )
                ]
            }

        self.values = {"report": _REPORT, "llm_calls": 2, "iterations": 1, "repairs": 0}
        self.next = ()
        return dict(self.values)

    def get_state(self, config):
        return SimpleNamespace(values=self.values, next=self.next, tasks=())


def _poll(client: TestClient, thread_id: str, target: str, attempts: int = 50) -> dict:
    for _ in range(attempts):
        resp = client.get(f"/research/{thread_id}")
        assert resp.status_code == 200
        body = resp.json()
        if body["status"] == target:
            return body
        time.sleep(0.02)
    raise AssertionError(f"未在限定时间内到达状态 {target}: {body}")


def test_health() -> None:
    with TestClient(create_api(graph=StubGraph())) as client:
        assert client.get("/health").json() == {"status": "ok"}


def test_index_serves_frontend() -> None:
    with TestClient(create_api(graph=StubGraph())) as client:
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Deep Research Agent" in resp.text
        assert 'id="researchForm"' in resp.text


def test_start_and_poll_to_completion() -> None:
    with TestClient(create_api(graph=StubGraph())) as client:
        resp = client.post("/research", json={"query": "测试问题"})
        assert resp.status_code == 202
        thread_id = resp.json()["thread_id"]

        body = _poll(client, thread_id, "completed")
        assert body["report"]["summary"] == "测试摘要"
        assert body["llm_calls"] == 2


def test_unknown_thread_returns_404() -> None:
    with TestClient(create_api(graph=StubGraph())) as client:
        assert client.get("/research/not-exist").status_code == 404


def test_hitl_interrupt_and_resume() -> None:
    with TestClient(create_api(graph=StubGraph(interrupt_first=True))) as client:
        resp = client.post("/research", json={"query": "测试问题"})
        thread_id = resp.json()["thread_id"]

        paused = _poll(client, thread_id, "interrupted")
        assert paused["interrupt"]["proposed_subtasks"] == ["甲", "乙", "丙"]

        resume = client.post(
            f"/research/{thread_id}/resume",
            json={"action": "approve"},
        )
        assert resume.status_code == 202

        done = _poll(client, thread_id, "completed")
        assert done["report"]["summary"] == "测试摘要"


def test_resume_finished_run_returns_409() -> None:
    with TestClient(create_api(graph=StubGraph())) as client:
        resp = client.post("/research", json={"query": "测试问题"})
        thread_id = resp.json()["thread_id"]
        _poll(client, thread_id, "completed")

        resp = client.post(f"/research/{thread_id}/resume", json={"action": "approve"})
        assert resp.status_code == 409
