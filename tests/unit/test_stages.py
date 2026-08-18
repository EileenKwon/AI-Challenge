"""T02 — 세션 상태머신 테스트."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from dn.domain.enums import FieldSource, SessionStage
from dn.domain.errors import StateTransitionError
from dn.domain.models import (
    AnalysisResult,
    CashflowResult,
    Debt,
    ExtractionResult,
    HouseholdProfile,
    IncomeProfile,
    SituationFlags,
)
from dn.domain.provenance import Tracked
from dn.pipeline.stages import assert_at_least, can_transition, transition


def _now() -> datetime:
    return datetime(2026, 8, 18, 12, 0, 0)


def _session(stage: SessionStage, **overrides: object):
    from dn.domain.models import SessionState

    base = dict(session_id="s1", stage=stage, created_at=_now(), updated_at=_now())
    base.update(overrides)
    return SessionState(**base)


def _tracked(value: object, confirmed: bool) -> Tracked:
    return Tracked(value=value, source=FieldSource.DOCUMENT, user_confirmed=confirmed)


def _confirmed_debt(confirmed: bool) -> Debt:
    from dn.domain.enums import ProductType

    return Debt(
        debt_id="d0",
        creditor=_tracked("A금융", confirmed),
        product_type=_tracked(ProductType.CREDIT_LOAN, confirmed),
        balance=_tracked(Decimal("1000000"), confirmed),
        overdue_days=_tracked(10, confirmed),
        is_secured=_tracked(False, confirmed),
    )


def _analysis_with_outputs() -> AnalysisResult:
    cashflow = CashflowResult(
        total_debt=Decimal("1000000"),
        monthly_total_payment=Decimal("100000"),
        monthly_available=Decimal("90000"),
        monthly_shortfall=Decimal("10000"),
    )
    return AnalysisResult(
        session_id="s1",
        analyzed_at=_now(),
        extraction=ExtractionResult(),
        income=IncomeProfile(),
        household=HouseholdProfile(),
        flags=SituationFlags(),
        cashflow=cashflow,
    )


# --- can_transition -------------------------------------------------------


def test_forward_adjacent_allowed() -> None:
    assert can_transition(SessionStage.S0_CONSENT, SessionStage.S1_UPLOADED) is True


def test_forward_skip_forbidden() -> None:
    assert can_transition(SessionStage.S0_CONSENT, SessionStage.S2_EXTRACTED) is False


def test_backward_any_distance_allowed() -> None:
    assert can_transition(SessionStage.S5_ANALYZED, SessionStage.S0_CONSENT) is True


def test_same_stage_not_a_transition() -> None:
    assert can_transition(SessionStage.S1_UPLOADED, SessionStage.S1_UPLOADED) is False


# --- transition() -----------------------------------------------------------


def test_illegal_skip_transition_raises() -> None:
    state = _session(SessionStage.S0_CONSENT)
    with pytest.raises(StateTransitionError):
        transition(state, SessionStage.S2_EXTRACTED)


def test_s2_to_s3_requires_all_fields_confirmed() -> None:
    state = _session(
        SessionStage.S2_EXTRACTED,
        extraction=ExtractionResult(debts=(_confirmed_debt(confirmed=False),)),
    )
    with pytest.raises(StateTransitionError):
        transition(state, SessionStage.S3_CONFIRMED)


def test_s2_to_s3_succeeds_when_all_confirmed() -> None:
    state = _session(
        SessionStage.S2_EXTRACTED,
        extraction=ExtractionResult(debts=(_confirmed_debt(confirmed=True),)),
    )
    new_state = transition(state, SessionStage.S3_CONFIRMED)
    assert new_state.stage == SessionStage.S3_CONFIRMED


def test_rollback_from_s5_invalidates_cashflow_rules_narrative() -> None:
    state = _session(SessionStage.S5_ANALYZED, analysis=_analysis_with_outputs())
    new_state = transition(state, SessionStage.S3_CONFIRMED)
    assert new_state.analysis is not None
    assert new_state.analysis.cashflow is None
    assert new_state.analysis.rules is None
    assert new_state.analysis.narrative is None
    # 다른 필드는 보존된다
    assert new_state.analysis.session_id == "s1"


def test_rollback_below_s5_does_not_touch_missing_analysis() -> None:
    state = _session(SessionStage.S1_UPLOADED)
    new_state = transition(state, SessionStage.S0_CONSENT)
    assert new_state.analysis is None


def test_original_state_is_not_mutated() -> None:
    state = _session(SessionStage.S0_CONSENT)
    transition(state, SessionStage.S1_UPLOADED)
    assert state.stage == SessionStage.S0_CONSENT


# --- assert_at_least ---------------------------------------------------------


def test_assert_at_least_passes_when_met() -> None:
    state = _session(SessionStage.S4_SUPPLEMENTED)
    assert_at_least(state, SessionStage.S3_CONFIRMED)  # 예외 없음


def test_assert_at_least_raises_when_not_met() -> None:
    state = _session(SessionStage.S1_UPLOADED)
    with pytest.raises(StateTransitionError):
        assert_at_least(state, SessionStage.S4_SUPPLEMENTED)
