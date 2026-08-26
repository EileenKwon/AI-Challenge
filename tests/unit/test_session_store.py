"""SqliteSessionStore — 세션 저장소의 SQLite 구현.

`InMemorySessionStore` 와 동일한 `SessionStore` 프로토콜을 만족하는지,
그리고 재시작(=새 인스턴스로 같은 DB 파일을 여는 것)에도 세션이 살아남는지 확인한다.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from dn.domain.enums import SessionStage
from dn.domain.models import SessionState
from dn.storage.session_store import SqliteSessionStore


def _make_session(session_id: str, updated_at: datetime) -> SessionState:
    return SessionState(
        session_id=session_id,
        stage=SessionStage.S0_CONSENT,
        created_at=updated_at,
        updated_at=updated_at,
    )


def test_get_missing_session_returns_none(tmp_path: Path) -> None:
    store = SqliteSessionStore(tmp_path / "sessions.db")
    assert store.get("no-such-session") is None


def test_create_then_get_round_trips(tmp_path: Path) -> None:
    store = SqliteSessionStore(tmp_path / "sessions.db")
    now = datetime(2026, 8, 27, 9, 0, 0)
    store.create(_make_session("s1", now))

    loaded = store.get("s1")

    assert loaded is not None
    assert loaded.session_id == "s1"
    assert loaded.stage == SessionStage.S0_CONSENT
    assert loaded.updated_at == now


def test_save_overwrites_existing_session(tmp_path: Path) -> None:
    store = SqliteSessionStore(tmp_path / "sessions.db")
    now = datetime(2026, 8, 27, 9, 0, 0)
    state = _make_session("s1", now)
    store.create(state)

    updated = state.model_copy(update={"stage": SessionStage.S1_UPLOADED})
    store.save(updated)

    loaded = store.get("s1")
    assert loaded is not None
    assert loaded.stage == SessionStage.S1_UPLOADED


def test_delete_removes_session(tmp_path: Path) -> None:
    store = SqliteSessionStore(tmp_path / "sessions.db")
    store.create(_make_session("s1", datetime(2026, 8, 27, 9, 0, 0)))

    store.delete("s1")

    assert store.get("s1") is None


def test_list_expired_returns_only_stale_sessions(tmp_path: Path) -> None:
    store = SqliteSessionStore(tmp_path / "sessions.db")
    now = datetime(2026, 8, 27, 12, 0, 0)
    store.create(_make_session("expired", now - timedelta(minutes=120)))
    store.create(_make_session("fresh", now - timedelta(minutes=5)))

    expired = store.list_expired(now=now, ttl_minutes=60)

    assert [s.session_id for s in expired] == ["expired"]


def test_session_survives_reopening_the_same_db_file(tmp_path: Path) -> None:
    """프로세스 재시작을 흉내낸다 — 새 `SqliteSessionStore` 인스턴스가 같은 파일을 연다."""
    db_path = tmp_path / "sessions.db"
    now = datetime(2026, 8, 27, 9, 0, 0)
    SqliteSessionStore(db_path).create(_make_session("s1", now))

    reopened = SqliteSessionStore(db_path)

    loaded = reopened.get("s1")
    assert loaded is not None
    assert loaded.session_id == "s1"
