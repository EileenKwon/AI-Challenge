"""세션 저장소.

`SessionStore` 프로토콜을 두 가지 구현으로 제공한다:
  - `InMemorySessionStore` — 테스트/데모용. 프로세스 종료 시 소실.
  - `SqliteSessionStore` — 기본 구현. TTL 만료 세션 조회를 지원한다.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol

from dn.domain.models import SessionState


class SessionStore(Protocol):
    def create(self, state: SessionState) -> None: ...

    def get(self, session_id: str) -> SessionState | None: ...

    def save(self, state: SessionState) -> None: ...

    def delete(self, session_id: str) -> None: ...

    def list_expired(self, *, now: datetime, ttl_minutes: int) -> list[SessionState]: ...


class InMemorySessionStore:
    """테스트·데모용 인메모리 구현."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}

    def create(self, state: SessionState) -> None:
        self._sessions[state.session_id] = state

    def get(self, session_id: str) -> SessionState | None:
        return self._sessions.get(session_id)

    def save(self, state: SessionState) -> None:
        self._sessions[state.session_id] = state

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def list_expired(self, *, now: datetime, ttl_minutes: int) -> list[SessionState]:
        cutoff = now - timedelta(minutes=ttl_minutes)
        return [s for s in self._sessions.values() if s.updated_at < cutoff]


class SqliteSessionStore:
    """기본 세션 저장소. 세션 전체를 JSON 직렬화해 단일 컬럼에 저장한다."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    updated_at TEXT NOT NULL,
                    data TEXT NOT NULL
                )
                """
            )

    def create(self, state: SessionState) -> None:
        self.save(state)

    def get(self, session_id: str) -> SessionState | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return None if row is None else SessionState.model_validate_json(row[0])

    def save(self, state: SessionState) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sessions (session_id, updated_at, data) VALUES (?, ?, ?)",
                (state.session_id, state.updated_at.isoformat(), state.model_dump_json()),
            )

    def delete(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))

    def list_expired(self, *, now: datetime, ttl_minutes: int) -> list[SessionState]:
        cutoff = (now - timedelta(minutes=ttl_minutes)).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT data FROM sessions WHERE updated_at < ?", (cutoff,)
            ).fetchall()
        return [SessionState.model_validate_json(r[0]) for r in rows]
