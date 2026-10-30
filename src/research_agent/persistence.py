"""图状态持久化：用 SqliteSaver 把每个超步的状态落盘。

一个 checkpointer 同时带来四个能力：断点续跑、崩溃恢复、时间旅行调试、
以及 human-in-the-loop（interrupt 必须依赖可持久化的状态）。

开发阶段用 SQLite 单文件；生产环境可换成 PostgresSaver，图代码不变。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

from research_agent.config import settings

_ALLOWED_MSGPACK = [("research_agent.state", "Finding")]


@contextmanager
def sqlite_saver(db_path: str | None = None) -> Iterator[SqliteSaver]:
    """打开 SQLite checkpoint 存储，退出 with 时自动关闭连接。"""
    path = db_path or settings.checkpoint_db_path
    serde = JsonPlusSerializer(allowed_msgpack_modules=_ALLOWED_MSGPACK)
    conn = sqlite3.connect(path, check_same_thread=False)
    try:
        yield SqliteSaver(conn, serde=serde)
    finally:
        conn.close()
