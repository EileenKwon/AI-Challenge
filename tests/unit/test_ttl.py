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


def test_rendered_scan_images_live_inside_the_session_dir(tmp_path, monkeypatch) -> None:
    """스캔 PDF 렌더링 이미지가 TTL 삭제 범위 안에 있어야 한다.

    렌더링 산출물을 `upload_dir` 바로 아래에 두면 스위퍼가 지우는
    `upload_dir/{session_id}/` 밖이라 영원히 남는다. 화면 01과 요약서가
    약속하는 "세션 종료 시 자동 삭제"가 깨지고, 사용자 조회서를 렌더링한
    이미지가 디스크에 계속 쌓인다 — 실제로 그런 상태였다.
    """
    import shutil
    from pathlib import Path
    from unittest.mock import patch

    from dn.ingest import pdf_reader
    from dn.settings import get_settings

    base = get_settings()
    settings = base.model_copy(
        update={
            "config": base.config.model_copy(
                update={"paths": base.config.paths.model_copy(update={"upload_dir": str(tmp_path)})}
            )
        }
    )

    session_dir = settings.upload_dir / "SESSION-123"
    session_dir.mkdir(parents=True)
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "sample_scanned.pdf"
    pdf = session_dir / "scan.pdf"
    shutil.copy(fixture, pdf)

    with patch("dn.ingest.pdf_reader.ocr_text_from_image", return_value="OCR"):
        document = pdf_reader.read(pdf, doc_id="d", settings=settings)

    rendered = [p for p in settings.upload_dir.rglob("*.png") if p.is_file()]
    assert rendered, "렌더링 이미지가 생성되지 않아 이 검사가 무의미하다"
    for image in rendered:
        assert session_dir in image.parents, f"세션 디렉터리 밖에 생성됨: {image}"

    # 세션 디렉터리를 통째로 지우면(= 스위퍼가 하는 일) 남는 파일이 없어야 한다
    assert document.pages[0].image_path is not None
    shutil.rmtree(session_dir)
    assert not [p for p in settings.upload_dir.rglob("*") if p.is_file()]
