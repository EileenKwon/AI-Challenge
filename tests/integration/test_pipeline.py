"""T18 — 분석 파이프라인 통합 테스트.

기획서 15장 김하늘 사례 엔드투엔드, 정책 카드 전부 verified:false 상태에서도
현금흐름이 반환되는지, 상태머신 위반 호출 시 409 가 나오는지 검증한다.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from dn.domain.enums import FieldSource, ProductType, SessionStage
from dn.domain.errors import PolicyCardError, StateTransitionError
from dn.domain.models import (
    Debt,
    ExtractionResult,
    HouseholdProfile,
    IncomeProfile,
    SessionState,
    SituationFlags,
)
from dn.domain.provenance import Tracked
from dn.main import create_app
from dn.pipeline.orchestrator import analyze
from dn.rules.policy_card import load_usable_cards
from dn.settings import get_settings


def _known(value):
    return Tracked(value=value, source=FieldSource.DOCUMENT)


def _kimhaneul_state(**overrides) -> SessionState:
    debts = (
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
        Debt(
            debt_id="d2",
            creditor=_known("C캐피탈"),
            product_type=_known(ProductType.CREDIT_LOAN),
            balance=_known(Decimal("7000000")),
            overdue_days=_known(0),
            is_secured=_known(False),
            monthly_payment=_known(Decimal("180000")),
        ),
    )
    now = datetime(2026, 8, 18)
    base = dict(
        session_id="kimhaneul",
        stage=SessionStage.S4_SUPPLEMENTED,
        created_at=now,
        updated_at=now,
        extraction=ExtractionResult(debts=debts),
        income=IncomeProfile(
            monthly_net_income=_known(Decimal("2500000")),
            has_continuous_income=_known(True),
        ),
        household=HouseholdProfile(essential_living_cost=_known(Decimal("1450000"))),
        flags=SituationFlags(),
    )
    base.update(overrides)
    return SessionState(**base)


# --- 김하늘 사례 엔드투엔드 -------------------------------------------------------


def test_kimhaneul_end_to_end_produces_expected_cashflow() -> None:
    state = _kimhaneul_state()
    result = analyze(state)

    assert result.cashflow is not None
    assert result.cashflow.total_debt == Decimal("46000000")
    assert result.cashflow.monthly_available == Decimal("1050000")
    assert result.cashflow.monthly_shortfall == Decimal("130000")
    assert result.cashflow.dti_ratio == Decimal("0.472")
    assert result.cashflow.max_overdue_days == 42


def test_kimhaneul_narrative_is_generated() -> None:
    result = analyze(_kimhaneul_state())
    assert result.narrative is not None
    assert len(result.narrative.sections) >= 1


def test_kimhaneul_rules_use_verified_false_cards_in_dev_mode() -> None:
    cards, dev_mode = load_usable_cards()
    assert all(c.verified is False for c in cards)
    assert dev_mode is True

    result = analyze(_kimhaneul_state())
    assert result.rules is not None
    assert result.rules.dev_mode is True


# --- 정책 카드 전부 verified:false 여도 현금흐름은 반환된다 ---------------------


def test_cashflow_returned_even_when_no_usable_policy_cards() -> None:
    """allow_unverified_cards 를 꺼서 verified:false 카드 6개가 전부 제외되는 상황을 만든다.

    이 경우 load_usable_cards() 는 PolicyCardError 를 던진다. 오케스트레이터는
    이를 삼키지 않고 undetermined=True 로 강등하되, cashflow 는 그대로 반환해야 한다.
    """
    base_settings = get_settings()
    disabled_rules = base_settings.config.rules.model_copy(update={"allow_unverified_cards": False})
    disabled_config = base_settings.config.model_copy(update={"rules": disabled_rules})
    disabled_settings = base_settings.model_copy(update={"config": disabled_config})

    with pytest.raises(PolicyCardError):
        load_usable_cards(settings=disabled_settings)

    state = _kimhaneul_state()
    result = analyze(state, settings=disabled_settings)

    assert result.cashflow is not None
    assert result.cashflow.total_debt == Decimal("46000000")
    assert result.cashflow.monthly_shortfall == Decimal("130000")
    assert result.rules is not None
    assert result.rules.undetermined is True


def test_state_below_s4_raises_state_transition_error() -> None:
    state = _kimhaneul_state(stage=SessionStage.S1_UPLOADED)
    with pytest.raises(StateTransitionError):
        analyze(state)


# --- HTTP: 상태머신 위반 호출 시 409 --------------------------------------------


def test_analyze_before_s4_returns_409_over_http() -> None:
    client = TestClient(create_app())

    created = client.post("/api/session")
    assert created.status_code == 201
    session_id = created.json()["session_id"]

    response = client.post(f"/api/session/{session_id}/analyze")
    assert response.status_code == 409


def test_analyze_missing_session_returns_404_over_http() -> None:
    client = TestClient(create_app())
    response = client.post("/api/session/does-not-exist/analyze")
    assert response.status_code == 404


def test_healthz_still_works_with_routers_mounted() -> None:
    client = TestClient(create_app())
    response = client.get("/healthz")
    assert response.status_code == 200
