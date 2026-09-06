"""상담용 요약서 PDF 생성 — 비동기 작업(job) API 테스트.

`POST /report` 가 PDF 를 직접 돌려주지 않고 202+job_id 로 바뀐 뒤(2026-09-06,
진행상태 UX 개선) 필요한 것들을 검증한다: 최초 생성, 캐시 재사용(재다운로드 시
재생성하지 않음), 옵션 변경 시 재생성, 생성 실패 처리, 진행 중 상태가 오류로
잘못 보이지 않는지, `session_stage` 가 작업이 실제로 끝난 뒤에만
`s7_reported` 로 바뀌는지.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from fastapi.testclient import TestClient

from dn.main import create_app
from dn.report import summary_pdf

_FIXTURE_PDF = Path(__file__).resolve().parents[1] / "fixtures" / "sample_text.pdf"


def _planned_session() -> tuple[TestClient, str]:
    client = TestClient(create_app())
    session_id = client.post("/api/session").json()["session_id"]
    client.post(f"/api/session/{session_id}/consent")
    with _FIXTURE_PDF.open("rb") as f:
        client.post(
            f"/api/session/{session_id}/document",
            files={"file": ("sample_text.pdf", f, "application/pdf")},
        )
    client.post(f"/api/session/{session_id}/confirm")
    client.post(
        f"/api/session/{session_id}/supplement",
        json={"monthly_net_income": 2500000, "essential_living_cost": 1450000},
    )
    client.post(f"/api/session/{session_id}/analyze")
    client.post(f"/api/session/{session_id}/plan")
    return client, session_id


def _poll_until_done(client: TestClient, session_id: str, job_id: str, *, timeout_s: float = 15.0):
    # 15초: 폰트 서브셋 캐시가 없는 최초 실행(다른 테스트가 캐시를 지운 직후 등)도
    # 안전하게 통과해야 한다 — 이 테스트들은 성능이 아니라 job 생애주기의
    # 정확성을 검증하는 것이 목적이다(실측 성능은 docs/report_timing.md).
    deadline = time.monotonic() + timeout_s
    status = None
    while time.monotonic() < deadline:
        status = client.get(
            f"/api/session/{session_id}/report/status", params={"job_id": job_id}
        ).json()
        if status["state"] in ("ready", "failed"):
            return status
        time.sleep(0.02)
    raise AssertionError(f"작업이 제한 시간 안에 끝나지 않았습니다: {status}")


def test_first_generation_succeeds_and_downloads() -> None:
    client, session_id = _planned_session()

    created = client.post(f"/api/session/{session_id}/report")
    assert created.status_code == 202
    body = created.json()
    assert body["state"] in ("preparing_data", "rendering_html", "rendering_pdf", "ready")
    assert body["total_steps"] == 4
    job_id = body["job_id"]

    status = _poll_until_done(client, session_id, job_id)
    assert status["state"] == "ready"
    assert status["progress"] == 100
    assert status["session_stage"] == "s7_reported"

    download = client.get(f"/api/session/{session_id}/report/download", params={"job_id": job_id})
    assert download.status_code == 200
    assert download.content.startswith(b"%PDF")


def test_session_stage_only_flips_to_reported_once_job_is_actually_ready() -> None:
    """2026-09-06 버그 리포트 — PDF 생성 중에는 아직 s6_planned 여야 한다."""
    client, session_id = _planned_session()

    created = client.post(f"/api/session/{session_id}/report")
    job_id = created.json()["job_id"]

    # 작업이 끝나기 전엔 세션이 아직 이전 단계여야 한다(캐시가 없는 상황이라
    # 몇 ms 는 preparing_data/rendering_html 에 머무를 가능성이 있다).
    first_status = client.get(
        f"/api/session/{session_id}/report/status", params={"job_id": job_id}
    ).json()
    if first_status["state"] != "ready":
        assert first_status["session_stage"] == "s6_planned"

    final_status = _poll_until_done(client, session_id, job_id)
    assert final_status["session_stage"] == "s7_reported"


def test_repeat_request_with_same_options_reuses_cached_job(monkeypatch) -> None:
    client, session_id = _planned_session()

    calls = {"n": 0}
    original = summary_pdf.render_pdf_from_html

    def _counting(html: str) -> bytes:
        calls["n"] += 1
        return original(html)

    monkeypatch.setattr(summary_pdf, "render_pdf_from_html", _counting)

    first = client.post(f"/api/session/{session_id}/report")
    job_id_1 = first.json()["job_id"]
    _poll_until_done(client, session_id, job_id_1)

    second = client.post(f"/api/session/{session_id}/report")
    assert second.status_code == 202
    assert second.json()["job_id"] == job_id_1
    assert second.json()["state"] == "ready"

    download = client.get(f"/api/session/{session_id}/report/download", params={"job_id": job_id_1})
    assert download.status_code == 200
    assert calls["n"] == 1, "같은 옵션으로 재요청했는데 PDF 를 다시 렌더링했다"


def test_option_change_triggers_regeneration_not_cache_hit(monkeypatch) -> None:
    client, session_id = _planned_session()

    calls = {"n": 0}
    original = summary_pdf.render_pdf_from_html

    def _counting(html: str) -> bytes:
        calls["n"] += 1
        return original(html)

    monkeypatch.setattr(summary_pdf, "render_pdf_from_html", _counting)

    first = client.post(f"/api/session/{session_id}/report", json={"include_income": True})
    job_id_1 = first.json()["job_id"]
    _poll_until_done(client, session_id, job_id_1)

    second = client.post(f"/api/session/{session_id}/report", json={"include_income": False})
    job_id_2 = second.json()["job_id"]
    assert job_id_2 != job_id_1
    _poll_until_done(client, session_id, job_id_2)

    assert calls["n"] == 2, "옵션을 바꿨는데 캐시를 재사용했다"


def test_generation_failure_reports_failed_state_without_leaking_details(monkeypatch) -> None:
    client, session_id = _planned_session()

    def _boom(html: str) -> bytes:
        raise RuntimeError("internal weasyprint stack trace with /app/var/secret/path")

    monkeypatch.setattr(summary_pdf, "render_pdf_from_html", _boom)

    created = client.post(f"/api/session/{session_id}/report")
    job_id = created.json()["job_id"]
    status = _poll_until_done(client, session_id, job_id)

    assert status["state"] == "failed"
    assert "다시 시도" in status["error"]
    assert "/app" not in status["error"]
    assert "RuntimeError" not in status["error"]

    download = client.get(f"/api/session/{session_id}/report/download", params={"job_id": job_id})
    assert download.status_code == 409

    # 실패했으므로 세션은 여전히 이전 단계에 머문다 — 진행 표시 마지막(7번째)
    # 칸이 완료(✓)가 아니라 예정(○, 회색)으로 남아야 한다는 요구사항과 대응된다.
    final = client.get(f"/api/session/{session_id}/report/status", params={"job_id": job_id}).json()
    assert final["state"] == "failed"
    plan_page = client.get(f"/web/session/{session_id}/plan")
    last_step = re.search(
        r'data-step-index="6".*?</li>', plan_page.text, re.DOTALL
    )
    assert last_step is not None, "7번째 진행 단계 항목을 찾지 못했습니다"
    assert "bg-slate-200" in last_step.group(0)
    assert "○" in last_step.group(0)
    assert "✓" not in last_step.group(0)


def test_in_progress_status_is_not_reported_as_error(monkeypatch) -> None:
    """느린 렌더링 도중 조회해도 오류가 아니라 정상 진행 상태여야 한다."""
    import threading

    release = threading.Event()
    original = summary_pdf.render_pdf_from_html

    def _slow(html: str) -> bytes:
        release.wait(timeout=5)
        return original(html)

    monkeypatch.setattr(summary_pdf, "render_pdf_from_html", _slow)

    client, session_id = _planned_session()
    created = client.post(f"/api/session/{session_id}/report")
    job_id = created.json()["job_id"]

    try:
        status = client.get(
            f"/api/session/{session_id}/report/status", params={"job_id": job_id}
        ).json()
        assert status["state"] in ("preparing_data", "rendering_html", "rendering_pdf")
        assert status["state"] != "failed"
    finally:
        release.set()
    _poll_until_done(client, session_id, job_id)


def test_download_before_ready_returns_409(monkeypatch) -> None:
    import threading

    release = threading.Event()
    original = summary_pdf.render_pdf_from_html

    def _slow(html: str) -> bytes:
        release.wait(timeout=5)
        return original(html)

    monkeypatch.setattr(summary_pdf, "render_pdf_from_html", _slow)

    client, session_id = _planned_session()
    created = client.post(f"/api/session/{session_id}/report")
    job_id = created.json()["job_id"]
    try:
        download = client.get(
            f"/api/session/{session_id}/report/download", params={"job_id": job_id}
        )
        assert download.status_code == 409
    finally:
        release.set()
    _poll_until_done(client, session_id, job_id)


def test_download_unknown_job_id_returns_404() -> None:
    client, session_id = _planned_session()
    r = client.get(
        f"/api/session/{session_id}/report/download", params={"job_id": "does-not-exist"}
    )
    assert r.status_code == 404


def test_status_unknown_job_id_returns_404() -> None:
    client, session_id = _planned_session()
    r = client.get(f"/api/session/{session_id}/report/status", params={"job_id": "does-not-exist"})
    assert r.status_code == 404
