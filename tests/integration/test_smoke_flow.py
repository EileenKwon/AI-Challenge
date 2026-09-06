"""T23 — 데모 시나리오 스모크 테스트 (pytest 버전).

`scripts/smoke.sh` 와 동일한 흐름(합성 문서 업로드 → 요약서 PDF 다운로드)을
`TestClient` 로 검증한다. Docker 컨테이너 기동은 이 환경에서 검증하지
못했지만(권한 없음), 애플리케이션 흐름 자체는 CI 에서도 매번 검증된다.
"""

from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from dn.main import create_app

_FIXTURE_PDF = Path(__file__).resolve().parents[1] / "fixtures" / "sample_text.pdf"


def _upload_and_wait(client: TestClient, session_id: str, filename: str, content: bytes) -> dict:
    """`POST /document`(202+job) → `GET /document/status` 폴링.

    `/document` 도 `/report` 와 같은 이유로(2026-09-06, 업로드 진행상태 UX
    개선 — 무료 LLM 티어 rate limit 재시도로 3~14초+ 걸릴 수 있음) 비동기
    작업으로 바뀌었다. 완료된 job 상태 dict(`session_stage`/`debt_count`
    포함)를 돌려준다.
    """
    created = client.post(
        f"/api/session/{session_id}/document",
        files={"file": (filename, content, "application/pdf")},
    )
    assert created.status_code == 202, created.text
    job_id = created.json()["job_id"]

    status = created.json()
    for _ in range(100):
        if status["state"] in ("ready", "failed"):
            break
        time.sleep(0.05)
        status = client.get(
            f"/api/session/{session_id}/document/status", params={"job_id": job_id}
        ).json()
    assert status["state"] == "ready", status
    return status


def _generate_and_download_report(client: TestClient, session_id: str) -> bytes:
    """`POST /report`(202+job) → `GET /report/status` 폴링 → `GET /report/download`.

    `/report` 가 PDF 를 직접 돌려주지 않고 비동기 작업으로 바뀐 뒤(2026-09-06,
    진행상태 UX 개선) 스모크 테스트도 같은 순서를 따라야 한다.
    """
    created = client.post(f"/api/session/{session_id}/report")
    assert created.status_code == 202, created.text
    job_id = created.json()["job_id"]

    status = created.json()
    for _ in range(100):
        if status["state"] in ("ready", "failed"):
            break
        time.sleep(0.05)
        status = client.get(
            f"/api/session/{session_id}/report/status", params={"job_id": job_id}
        ).json()
    assert status["state"] == "ready", status

    download = client.get(f"/api/session/{session_id}/report/download", params={"job_id": job_id})
    assert download.status_code == 200
    return download.content


def test_full_demo_scenario_upload_to_pdf_download() -> None:
    client = TestClient(create_app())

    created = client.post("/api/session")
    assert created.status_code == 201
    session_id = created.json()["session_id"]

    assert client.post(f"/api/session/{session_id}/consent").status_code == 200

    _upload_and_wait(client, session_id, "sample_text.pdf", _FIXTURE_PDF.read_bytes())

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

    pdf_bytes = _generate_and_download_report(client, session_id)
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1000


def test_report_before_plan_returns_409() -> None:
    """상태머신을 건너뛰면(계획 단계 생략) 409 여야 한다 — smoke.sh 가 처음에 잡아낸 버그."""
    client = TestClient(create_app())

    created = client.post("/api/session")
    session_id = created.json()["session_id"]
    client.post(f"/api/session/{session_id}/consent")
    _upload_and_wait(client, session_id, "sample_text.pdf", _FIXTURE_PDF.read_bytes())
    client.post(f"/api/session/{session_id}/confirm")
    client.post(
        f"/api/session/{session_id}/supplement",
        json={"monthly_net_income": 2500000, "essential_living_cost": 1450000},
    )
    client.post(f"/api/session/{session_id}/analyze")

    response = client.post(f"/api/session/{session_id}/report")  # /plan 건너뜀
    assert response.status_code == 409


# --- 실제 LLM 백엔드처럼 채무가 나오는 경우 -------------------------------------
#
# 위 시나리오는 기본 StubClient 로 돈다. StubClient 는 채무 0건을 돌려주므로
# `/confirm` 이 확인할 필드가 없어 그냥 통과한다 — 그래서 이 테스트도,
# scripts/smoke.sh 도 "실제 LLM 을 붙이면 409 로 죽는" 상태를 오래 못 잡았다.
# 채무가 나오는 백엔드를 세워 같은 흐름을 다시 검증한다.

_CONFIRM_FIELDS = ("creditor", "product_type", "balance", "overdue_days", "is_secured")

_THREE_DEBTS = """{"debts": [
  {"creditor": "가나캐피탈", "product_type": "신용대출", "balance": "21,470,000원",
   "executed_at": "2022-07-22", "overdue_days": 77, "is_secured": false},
  {"creditor": "다라파이낸스", "product_type": "담보대출", "balance": "35,140,000원",
   "executed_at": "2020-05-01", "overdue_days": 43, "is_secured": true},
  {"creditor": "마바캐피탈", "product_type": "리볼빙", "balance": "25,280,000원",
   "executed_at": "2020-11-14", "overdue_days": 42, "is_secured": false}
]}"""


def _client_with_extracting_backend() -> TestClient:
    from dn.api.deps import get_llm_client_dep
    from dn.llm.client import StubClient

    app = create_app()
    app.dependency_overrides[get_llm_client_dep] = lambda: StubClient(
        lambda system, user: _THREE_DEBTS if "신용정보조회서" in user or "채무" in user else "{}"
    )
    return TestClient(app)


def _uploaded_session(client: TestClient) -> str:
    session_id = client.post("/api/session").json()["session_id"]
    client.post(f"/api/session/{session_id}/consent")
    status = _upload_and_wait(client, session_id, "sample_text.pdf", _FIXTURE_PDF.read_bytes())
    assert status["debt_count"] == 3
    return session_id


def test_confirm_requires_field_confirmations_when_debts_exist() -> None:
    """확인 PATCH 없이 /confirm 을 부르면 409 — scripts/smoke.sh 가 깨졌던 지점."""
    client = _client_with_extracting_backend()
    session_id = _uploaded_session(client)

    assert client.post(f"/api/session/{session_id}/confirm").status_code == 409


def test_full_demo_scenario_with_extracted_debts() -> None:
    """화면 03 · smoke.sh 와 같은 순서(PATCH → confirm)로 끝까지 간다."""
    client = _client_with_extracting_backend()
    session_id = _uploaded_session(client)

    debts = client.get(f"/api/session/{session_id}/extraction").json()["debts"]
    confirmations = [
        {"debt_index": i, "field_name": field, "user_confirmed": True}
        for i in range(len(debts))
        for field in _CONFIRM_FIELDS
    ]
    assert (
        client.patch(f"/api/session/{session_id}/extraction", json=confirmations).status_code == 200
    )
    assert client.post(f"/api/session/{session_id}/confirm").status_code == 200

    assert (
        client.post(
            f"/api/session/{session_id}/supplement",
            json={
                "monthly_net_income": 2500000,
                "essential_living_cost": 1450000,
                "income_proof_available": True,
                "debts": [{"debt_index": i, "monthly_payment": 350000} for i in range(3)],
            },
        ).status_code
        == 200
    )
    assert client.post(f"/api/session/{session_id}/analyze").status_code == 200
    assert client.post(f"/api/session/{session_id}/plan").status_code == 200

    pdf_bytes = _generate_and_download_report(client, session_id)
    assert pdf_bytes.startswith(b"%PDF")
