"""T23 — 데모 시나리오 스모크 테스트 (pytest 버전).

`scripts/smoke.sh` 와 동일한 흐름(합성 문서 업로드 → 요약서 PDF 다운로드)을
`TestClient` 로 검증한다. Docker 컨테이너 기동은 이 환경에서 검증하지
못했지만(권한 없음), 애플리케이션 흐름 자체는 CI 에서도 매번 검증된다.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from dn.main import create_app

_FIXTURE_PDF = Path(__file__).resolve().parents[1] / "fixtures" / "sample_text.pdf"


def test_full_demo_scenario_upload_to_pdf_download() -> None:
    client = TestClient(create_app())

    created = client.post("/api/session")
    assert created.status_code == 201
    session_id = created.json()["session_id"]

    assert client.post(f"/api/session/{session_id}/consent").status_code == 200

    with _FIXTURE_PDF.open("rb") as f:
        upload = client.post(
            f"/api/session/{session_id}/document",
            files={"file": ("sample_text.pdf", f, "application/pdf")},
        )
    assert upload.status_code == 200, upload.text

    assert client.post(f"/api/session/{session_id}/confirm").status_code == 200

    supplement = client.post(
        f"/api/session/{session_id}/supplement",
        json={
            "monthly_net_income": 2500000,
            "essential_living_cost": 1450000,
            "income_proof_available": True,
        },
    )
    assert supplement.status_code == 200

    assert client.post(f"/api/session/{session_id}/analyze").status_code == 200
    assert client.post(f"/api/session/{session_id}/plan").status_code == 200

    report = client.post(f"/api/session/{session_id}/report")
    assert report.status_code == 200
    assert report.content.startswith(b"%PDF")
    assert len(report.content) > 1000


def test_report_before_plan_returns_409() -> None:
    """상태머신을 건너뛰면(계획 단계 생략) 409 여야 한다 — smoke.sh 가 처음에 잡아낸 버그."""
    client = TestClient(create_app())

    created = client.post("/api/session")
    session_id = created.json()["session_id"]
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

    response = client.post(f"/api/session/{session_id}/report")  # /plan 건너뜀
    assert response.status_code == 409
