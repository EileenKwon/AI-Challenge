"""문서 업로드 → 추출 — 비동기 작업(job) API 테스트.

`POST /document` 가 추출 결과를 직접 돌려주지 않고 202+job_id 로 바뀐 뒤
(2026-09-06, 업로드 진행상태 UX 개선 — 무료 LLM 티어 rate limit 재시도로
3~14초+ 걸릴 수 있음, 실측) 필요한 것들을 검증한다.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient

from dn.main import create_app

_FIXTURE_PDF = Path(__file__).resolve().parents[1] / "fixtures" / "sample_text.pdf"


def _consented_session() -> tuple[TestClient, str]:
    client = TestClient(create_app())
    session_id = client.post("/api/session").json()["session_id"]
    client.post(f"/api/session/{session_id}/consent")
    return client, session_id


def _poll_until_done(client: TestClient, session_id: str, job_id: str, *, timeout_s: float = 15.0):
    deadline = time.monotonic() + timeout_s
    status = None
    while time.monotonic() < deadline:
        status = client.get(
            f"/api/session/{session_id}/document/status", params={"job_id": job_id}
        ).json()
        if status["state"] in ("ready", "failed"):
            return status
        time.sleep(0.02)
    raise AssertionError(f"업로드 작업이 제한 시간 안에 끝나지 않았습니다: {status}")


def test_upload_returns_202_with_job_id_immediately() -> None:
    client, session_id = _consented_session()
    with _FIXTURE_PDF.open("rb") as f:
        r = client.post(
            f"/api/session/{session_id}/document",
            files={"file": ("sample_text.pdf", f, "application/pdf")},
        )
    assert r.status_code == 202
    body = r.json()
    assert "job_id" in body
    assert body["state"] in ("reading_document", "checking_content", "extracting_debts", "ready")
    assert body["total_steps"] == 4


def test_document_status_for_unknown_job_returns_404() -> None:
    client, session_id = _consented_session()
    r = client.get(f"/api/session/{session_id}/document/status", params={"job_id": "no-such-job"})
    assert r.status_code == 404


def test_document_status_for_other_sessions_job_returns_404() -> None:
    """job_id 가 실재해도 다른 세션 소유면 노출하지 않는다."""
    client, session_id = _consented_session()
    with _FIXTURE_PDF.open("rb") as f:
        created = client.post(
            f"/api/session/{session_id}/document",
            files={"file": ("sample_text.pdf", f, "application/pdf")},
        )
    job_id = created.json()["job_id"]
    _poll_until_done(client, session_id, job_id)

    _, other_session_id = _consented_session()
    r = client.get(f"/api/session/{other_session_id}/document/status", params={"job_id": job_id})
    assert r.status_code == 404


def test_session_stage_stays_before_extracted_until_job_actually_ready() -> None:
    """느린 추출 도중에는 세션이 아직 이전 단계여야 한다."""
    release = threading.Event()
    import dn.ingest.jobs as upload_jobs

    original_extract = upload_jobs.extract

    def _slow_extract(document, *, client):
        release.wait(timeout=5)
        return original_extract(document, client=client)

    client, session_id = _consented_session()
    try:
        upload_jobs.extract = _slow_extract
        with _FIXTURE_PDF.open("rb") as f:
            created = client.post(
                f"/api/session/{session_id}/document",
                files={"file": ("sample_text.pdf", f, "application/pdf")},
            )
        job_id = created.json()["job_id"]

        first_status = client.get(
            f"/api/session/{session_id}/document/status", params={"job_id": job_id}
        ).json()
        assert first_status["state"] != "ready"
        extraction = client.get(f"/api/session/{session_id}/extraction").json()
        assert extraction["debts"] == []
    finally:
        release.set()
        upload_jobs.extract = original_extract
    final_status = _poll_until_done(client, session_id, job_id)
    assert final_status["state"] == "ready"
    assert final_status["session_stage"] == "s2_extracted"


def test_manual_entry_stays_synchronous_not_a_job() -> None:
    """직접 입력은 LLM 을 쓰지 않아 느릴 이유가 없다 — job 화하지 않는다."""
    client, session_id = _consented_session()
    r = client.post(
        f"/api/session/{session_id}/manual-debts",
        json={"debts": [{"creditor": "OO캐피탈"}]},
    )
    assert r.status_code == 200
    assert r.json()["stage"] == "s2_extracted"
