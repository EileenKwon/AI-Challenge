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


def test_kimhaneul_income_drop_scenario_is_attached() -> None:
    result = analyze(_kimhaneul_state())

    assert result.scenario is not None
    assert result.scenario.scenario_id == "income_drop_20"
    assert result.scenario.before.monthly_shortfall == Decimal("130000")
    assert result.scenario.after.monthly_shortfall == Decimal("630000")


def test_scenario_stays_attached_even_when_income_unknown() -> None:
    state = _kimhaneul_state(income=IncomeProfile())
    result = analyze(state)

    assert result.scenario is not None
    assert result.scenario.before.dti_ratio is None
    assert result.scenario.after.dti_ratio is None


def test_kimhaneul_narrative_is_generated() -> None:
    result = analyze(_kimhaneul_state())
    assert result.narrative is not None
    assert len(result.narrative.sections) >= 1


def test_dev_mode_flags_remaining_unverified_card() -> None:
    """미검증 카드가 하나라도 남아 있으면 dev_mode 로 표시된다.

    2026-08-21 대조로 6개 중 5개가 verified 로 전환되었고, 개인워크아웃만
    총채무액 한도 출처 충돌로 미검증 상태다. dev_mode 는 그 사실을 드러내는
    신호이므로 '전부 미검증'이 아니라 '하나라도 미검증'을 검사한다.
    """
    cards, dev_mode = load_usable_cards()
    unverified = [c.id for c in cards if not c.verified]
    assert unverified == ["personal_workout"], f"예상과 다른 미검증 카드: {unverified}"
    assert dev_mode is True

    result = analyze(_kimhaneul_state())
    assert result.rules is not None
    assert result.rules.dev_mode is True


# --- 정책 카드 전부 verified:false 여도 현금흐름은 반환된다 ---------------------


def test_cashflow_returned_even_when_no_usable_policy_cards(tmp_path) -> None:
    """사용 가능한 정책 카드가 0개인 상황에서도 현금흐름은 반환되어야 한다.

    이전에는 카드 6개가 전부 미검증이라 allow_unverified_cards 를 끄는 것만으로
    0개 상황을 만들 수 있었다. 대조 완료 후 5개가 verified 이므로, 빈 카드
    디렉터리를 가리켜 같은 상황을 재현한다.

    핵심 불변조건은 그대로다 — 제도 판정이 불가능해도 상환여력 계산 결과는
    독립적인 가치를 가지므로 반드시 제공된다(기획서 7.3).
    """
    import shutil

    base_settings = get_settings()
    src_dir = base_settings.resolve(base_settings.config.paths.policy_card_dir)
    version = base_settings.config.paths.policy_card_version

    empty_root = tmp_path / "policy_cards"
    (empty_root / version).mkdir(parents=True)
    # 스키마 파일은 로더가 요구하므로 그대로 복사하고 카드만 비운다.
    shutil.copy(src_dir / "_schema.yaml", empty_root / "_schema.yaml")
    if (src_dir / version / "_schema.yaml").exists():
        shutil.copy(src_dir / version / "_schema.yaml", empty_root / version / "_schema.yaml")

    disabled_rules = base_settings.config.rules.model_copy(update={"allow_unverified_cards": False})
    disabled_paths = base_settings.config.paths.model_copy(
        update={"policy_card_dir": str(empty_root)}
    )
    disabled_config = base_settings.config.model_copy(
        update={"rules": disabled_rules, "paths": disabled_paths}
    )
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
