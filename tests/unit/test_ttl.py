"""T02 — TTL 만료 세션·업로드 원본 삭제 테스트."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from dn.domain.enums import SessionStage
from dn.domain.models import SessionState
from dn.storage.session_store import InMemorySessionStore
from dn.storage.ttl import session_upload_dir, sweep_expired_sessions


def _make_session(session_id: str, updated_at: datetime) -> SessionState:
    return SessionState(
        session_id=session_id,
        stage=SessionStage.S1_UPLOADED,
        created_at=updated_at,
        updated_at=updated_at,
    )


def test_expired_session_upload_files_are_deleted(tmp_path: Path) -> None:
    upload_dir = tmp_path / "uploads"
    now = datetime(2026, 8, 18, 12, 0, 0)
    ttl_minutes = 60

    expired_id = "expired-session"
    fresh_id = "fresh-session"

    expired_dir = session_upload_dir(upload_dir, expired_id)
    expired_dir.mkdir(parents=True)
    (expired_dir / "credit_report.pdf").write_bytes(b"dummy")

    fresh_dir = session_upload_dir(upload_dir, fresh_id)
    fresh_dir.mkdir(parents=True)
    (fresh_dir / "credit_report.pdf").write_bytes(b"dummy")

    store = InMemorySessionStore()
    store.create(_make_session(expired_id, now - timedelta(minutes=120)))
    store.create(_make_session(fresh_id, now - timedelta(minutes=5)))

    deleted = sweep_expired_sessions(store, now=now, ttl_minutes=ttl_minutes, upload_dir=upload_dir)

    assert deleted == [expired_id]
    assert not expired_dir.exists()
    assert fresh_dir.exists()
    assert store.get(expired_id) is None
    assert store.get(fresh_id) is not None


def test_sweep_is_noop_when_nothing_expired(tmp_path: Path) -> None:
    upload_dir = tmp_path / "uploads"
    now = datetime(2026, 8, 18, 12, 0, 0)
    store = InMemorySessionStore()
    store.create(_make_session("s1", now - timedelta(minutes=1)))

    deleted = sweep_expired_sessions(store, now=now, ttl_minutes=60, upload_dir=upload_dir)

    assert deleted == []
    assert store.get("s1") is not None


def test_sweep_handles_missing_upload_dir_gracefully(tmp_path: Path) -> None:
    upload_dir = tmp_path / "uploads"
    now = datetime(2026, 8, 18, 12, 0, 0)
    store = InMemorySessionStore()
    store.create(_make_session("no-files", now - timedelta(minutes=120)))

    deleted = sweep_expired_sessions(store, now=now, ttl_minutes=60, upload_dir=upload_dir)

    assert deleted == ["no-files"]
    assert store.get("no-files") is None
