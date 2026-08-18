"""T19 — 화면 7종 렌더링 테스트.

이 테스트는 Jinja2 템플릿이 실제 세션 데이터로 예외 없이 렌더링되고 화면별
필수 요소가 HTML에 포함되는지까지만 검증한다. "모바일 뷰포트(375px)에서
가로 스크롤 없음"과 "수동 워크스루"는 실제 브라우저 렌더링 확인이 필요한데
이 환경에는 브라우저가 없어 이 테스트로는 검증하지 못한다 — CLAUDE 확인 필요.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from dn.api.deps import get_session_store
from dn.domain.enums import FieldSource, PathStatus, ProductType, SessionStage
from dn.domain.models import (
    ActionItem,
    ActionPlan,
    AnalysisResult,
    CashflowResult,
    Debt,
    ExtractionResult,
    GapReport,
    HouseholdProfile,
    IncomeProfile,
    Narrative,
    NarrativeSection,
    PathCandidate,
    PolicyRef,
    RuleEngineResult,
    SessionState,
    SituationFlags,
)
from dn.domain.provenance import Tracked
from dn.main import create_app


def _known(value):
    return Tracked(value=value, source=FieldSource.DOCUMENT)


def _debts():
    return (
        Debt(
            debt_id="d0",
            creditor=_known("A금융"),
            product_type=_known(ProductType.CREDIT_LOAN),
            balance=_known(Decimal("25000000")),
            overdue_days=_known(42),
            is_secured=_known(False),
            monthly_payment=_known(Decimal("620000")),
        ),
        Debt(
            debt_id="d1",
            creditor=_known("B카드"),
            product_type=_known(ProductType.CARD_LOAN),
            balance=_known(Decimal("14000000")),
            overdue_days=_known(0),
            is_secured=_known(False),
            monthly_payment=_known(Decimal("380000")),
        ),
    )


def _full_state(session_id: str) -> SessionState:
    now = datetime(2026, 8, 18)
    extraction = ExtractionResult(debts=_debts())
    cashflow = CashflowResult(
        total_debt=Decimal("39000000"),
        monthly_total_payment=Decimal("1000000"),
        monthly_available=Decimal("800000"),
        monthly_shortfall=Decimal("200000"),
        dti_ratio=Decimal("0.4"),
        max_overdue_days=42,
    )
    paths = (
        PathCandidate(
            path_id="pre_debt_adjustment",
            name="사전채무조정",
            priority=2,
            agency="신용회복위원회",
            status=PathStatus.NEEDS_INFO,
            consult_questions=("예상 납입기간은?",),
            policy_ref=PolicyRef(
                card_id="pre_debt_adjustment",
                card_version="2026-08-13.1",
                title="사전채무조정",
                policy_base_date=date(2026, 8, 13),
                verified=False,
            ),
        ),
    )
    plan = ActionPlan(
        items=(ActionItem(timing="today", order=1, text="추출된 채무 목록과 연체일수 확인"),)
    )
    narrative = Narrative(
        sections=(
            NarrativeSection(
                section="cashflow", text="매달 20만 원이 부족합니다.", generated_by_llm=False
            ),
        )
    )
    analysis = AnalysisResult(
        session_id=session_id,
        analyzed_at=now,
        extraction=extraction,
        income=IncomeProfile(monthly_net_income=_known(Decimal("2000000"))),
        household=HouseholdProfile(essential_living_cost=_known(Decimal("1200000"))),
        flags=SituationFlags(),
        cashflow=cashflow,
        rules=RuleEngineResult(paths=paths, policy_base_date=date(2026, 8, 13)),
        narrative=narrative,
        plan=plan,
        gaps=GapReport(),
    )
    return SessionState(
        session_id=session_id,
        stage=SessionStage.S7_REPORTED,
        created_at=now,
        updated_at=now,
        extraction=extraction,
        income=IncomeProfile(monthly_net_income=_known(Decimal("2000000"))),
        household=HouseholdProfile(essential_living_cost=_known(Decimal("1200000"))),
        flags=SituationFlags(),
        analysis=analysis,
    )


def _client_with_session() -> tuple[TestClient, str]:
    client = TestClient(create_app())
    state = _full_state("web-test-session")
    get_session_store().create(state)
    return client, state.session_id


def test_intro_page_renders_required_elements() -> None:
    client, sid = _client_with_session()
    r = client.get(f"/web/session/{sid}/intro")
    assert r.status_code == 200
    assert "유의사항" in r.text
    assert "개인정보 처리" in r.text
    assert "크레딧포유" in r.text


def test_upload_page_renders_four_input_methods() -> None:
    client, sid = _client_with_session()
    r = client.get(f"/web/session/{sid}/upload")
    assert r.status_code == 200
    for marker in ("PDF 파일 업로드", "사진(이미지) 업로드", "데모용 합성 문서", "직접 입력"):
        assert marker in r.text


def test_extraction_page_shows_source_badges() -> None:
    client, sid = _client_with_session()
    r = client.get(f"/web/session/{sid}/extraction")
    assert r.status_code == 200
    assert "A금융" in r.text
    assert "문서" in r.text  # source badge label
    assert "전체 확인 완료" in r.text


def test_supplement_page_shows_five_fixed_questions() -> None:
    client, sid = _client_with_session()
    r = client.get(f"/web/session/{sid}/supplement")
    assert r.status_code == 200
    assert "모름" in r.text
    assert "월 실수령소득은 얼마인가?" in r.text


def test_result_page_shows_confirmed_numbers_and_trace() -> None:
    client, sid = _client_with_session()
    r = client.get(f"/web/session/{sid}/result")
    assert r.status_code == 200
    assert "확정 숫자" in r.text
    assert "20만 원" in r.text
    assert "이 숫자는 어디서 왔나요" in r.text


def test_paths_page_shows_eleven_item_card() -> None:
    client, sid = _client_with_session()
    r = client.get(f"/web/session/{sid}/paths")
    assert r.status_code == 200
    assert "사전채무조정" in r.text
    assert "검토 후보 (확정 아님)" in r.text
    assert "정책 기준일" in r.text


def test_plan_page_shows_plan_and_pdf_download() -> None:
    client, sid = _client_with_session()
    r = client.get(f"/web/session/{sid}/plan")
    assert r.status_code == 200
    assert "추출된 채무 목록과 연체일수 확인" in r.text
    assert "PDF 다운로드" in r.text
    assert "포함할 항목을 선택" in r.text


def test_dev_mode_banner_shown_when_allow_unverified_cards_enabled() -> None:
    client, sid = _client_with_session()
    r = client.get(f"/web/session/{sid}/result")
    assert "개발 모드" in r.text


def test_missing_session_returns_404_for_web_pages() -> None:
    client = TestClient(create_app())
    r = client.get("/web/session/does-not-exist/result")
    assert r.status_code == 404


def test_all_seven_screens_render_without_500() -> None:
    client, sid = _client_with_session()
    for path in ("intro", "upload", "extraction", "supplement", "result", "paths", "plan"):
        r = client.get(f"/web/session/{sid}/{path}")
        assert r.status_code == 200, f"{path} 화면 렌더링 실패"
