"""T07 — 3단계 질문(고정 5문항 + 조건부 3문항) 테스트."""

from __future__ import annotations

from dn.domain.enums import FieldSource
from dn.domain.models import Debt, SituationFlags
from dn.domain.provenance import Tracked
from dn.reconcile.questions import (
    has_income_drop_signal,
    has_overdue,
    has_secured_debt,
    load_conditional_questions,
    load_fixed_questions,
    select_active_questions,
)


def test_exactly_five_fixed_questions() -> None:
    assert len(load_fixed_questions()) == 5


def test_exactly_three_conditional_questions() -> None:
    assert len(load_conditional_questions()) == 3


def test_select_active_questions_without_triggers_returns_only_fixed() -> None:
    active = select_active_questions(
        secured_debt_present=False, overdue_present=False, income_drop_present=False
    )
    assert len(active) == 5


def test_select_active_questions_with_all_triggers_returns_eight() -> None:
    active = select_active_questions(
        secured_debt_present=True, overdue_present=True, income_drop_present=True
    )
    assert len(active) == 8


def test_select_active_questions_with_one_trigger_adds_one() -> None:
    active = select_active_questions(
        secured_debt_present=True, overdue_present=False, income_drop_present=False
    )
    assert len(active) == 6
    assert any(q.qid == "C1_COLLATERAL" for q in active)


def test_has_secured_debt_detects_true_flag() -> None:
    secured = Debt(debt_id="d0", is_secured=Tracked(value=True, source=FieldSource.DOCUMENT))
    unsecured = Debt(debt_id="d1", is_secured=Tracked(value=False, source=FieldSource.DOCUMENT))
    assert has_secured_debt((secured, unsecured)) is True
    assert has_secured_debt((unsecured,)) is False


def test_has_overdue_detects_positive_days() -> None:
    overdue = Debt(debt_id="d0", overdue_days=Tracked(value=10, source=FieldSource.DOCUMENT))
    not_overdue = Debt(debt_id="d1", overdue_days=Tracked(value=0, source=FieldSource.DOCUMENT))
    assert has_overdue((overdue,)) is True
    assert has_overdue((not_overdue,)) is False


def test_has_income_drop_signal_from_job_loss_or_business_closed() -> None:
    job_loss = SituationFlags(recent_job_loss=Tracked(value=True, source=FieldSource.USER_INPUT))
    neither = SituationFlags()
    assert has_income_drop_signal(job_loss) is True
    assert has_income_drop_signal(neither) is False
