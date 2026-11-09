from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from app.agent.models import Message

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role       TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);

CREATE TABLE IF NOT EXISTS handoffs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT NOT NULL,
    reason        TEXT NOT NULL,
    summary       TEXT NOT NULL,
    customer_name TEXT,
    contact       TEXT,
    order_id      INTEGER,
    status        TEXT NOT NULL DEFAULT 'open',
    created_at    TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ConversationStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    # --- mensagens ---------------------------------------------------------------
    def append(self, session_id: str, role: str, content: str) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (session_id, role, content, _now()),
            )

    def history(self, session_id: str, limit: int = 20) -> list[Message]:
        """Últimas `limit` mensagens, em ordem cronológica, começando sempre por uma do cliente."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        messages = [Message(role=r["role"], text=r["content"]) for r in reversed(rows)]
        while messages and messages[0].role != "user":
            messages.pop(0)
        return messages

    def clear(self, session_id: str) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))

    # --- encaminhamentos ---------------------------------------------------------
    def create_handoff(
        self,
        session_id: str,
        reason: str,
        summary: str,
        customer_name: str | None = None,
        contact: str | None = None,
        order_id: int | None = None,
    ) -> int:
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute(
                "INSERT INTO handoffs (session_id, reason, summary, customer_name, contact, order_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session_id, reason, summary, customer_name, contact, order_id, _now()),
            )
            return int(cursor.lastrowid)

    def list_handoffs(self, status: str | None = None) -> list[dict]:
        sql, params = "SELECT * FROM handoffs", ()
        if status:
            sql, params = sql + " WHERE status = ?", (status,)
        with closing(self._connect()) as conn:
            return [dict(r) for r in conn.execute(sql + " ORDER BY id", params)]
