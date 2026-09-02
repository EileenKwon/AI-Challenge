"""T08 — 현금흐름 계산 단위 테스트: 결측 3종 시나리오, 소득 0, float 입력 거부."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from dn.cashflow.calculator import compute
from dn.domain.enums import FieldSource
from dn.domain.models import Debt, HouseholdProfile, IncomeProfile
from dn.domain.provenance import Tracked


def _known(value):
    return Tracked(value=value, source=FieldSource.DOCUMENT)


def _unknown():
    return Tracked()


def _debt(*, balance=Decimal("1000000"), monthly_payment=Decimal("100000"), overdue_days=0) -> Debt:
    return Debt(
        debt_id="d0",
        creditor=_known("A금융"),
        balance=_known(balance) if balance is not None else _unknown(),
        overdue_days=_known(overdue_days),
        is_secured=_known(False),
        monthly_payment=_known(monthly_payment) if monthly_payment is not None else _unknown(),
    )


def _income(*, monthly_net_income=Decimal("2000000")) -> IncomeProfile:
    return IncomeProfile(
        monthly_net_income=(
            _known(monthly_net_income) if monthly_net_income is not None else _unknown()
        )
    )


def _household(*, essential_living_cost=Decimal("1000000")) -> HouseholdProfile:
    return HouseholdProfile(essential_living_cost=_known(essential_living_cost))


# --- 결측 3종 시나리오 ---------------------------------------------------------


def test_missing_monthly_payment_excludes_debt_from_sum() -> None:
    debts = (
        _debt(monthly_payment=Decimal("100000")),
        Debt(
            debt_id="d1",
            creditor=_known("B카드"),
            balance=_known(Decimal("500000")),
            monthly_payment=_unknown(),
        ),
    )
    result = compute(debts, _income(), _household())

    assert result.monthly_total_payment == Decimal("100000")
    assert len(result.excluded_items) == 1
    assert "B카드" in result.excluded_items[0]


def test_missing_monthly_net_income_yields_none_dti_and_zero_treated_as_assumption() -> None:
    result = compute((_debt(),), _income(monthly_net_income=None), _household())

    assert result.dti_ratio is None
    assert any("월 실수령소득" in note for note in result.assumptions)
    # avail 은 항상 확정 숫자여야 한다 (미입력 항목은 0 처리)
    assert result.monthly_available == Decimal("-1000000")  # 0 - 1,000,000(생활비)


def test_missing_optional_household_field_defaults_to_zero_with_assumption() -> None:
    household = HouseholdProfile(
        essential_living_cost=_known(Decimal("1000000")),
        medical_care_cost=_unknown(),
    )
    result = compute((_debt(),), _income(), household)

    assert any("의료·돌봄비" in note for note in result.assumptions)
    assert result.monthly_available == Decimal("1000000")  # 2,000,000 - 1,000,000 - 0(의료비)


# --- 소득 0일 때 dti_ratio is None ---------------------------------------------


def test_zero_income_yields_none_dti_ratio() -> None:
    result = compute((_debt(),), _income(monthly_net_income=Decimal("0")), _household())
    assert result.dti_ratio is None


def test_positive_income_yields_computed_dti_ratio() -> None:
    result = compute((_debt(monthly_payment=Decimal("500000")),), _income(), _household())
    assert result.dti_ratio == Decimal("0.250")


# --- float 입력 거부 -----------------------------------------------------------


def test_float_balance_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Debt(debt_id="d0", balance=Tracked(value=25_000_000.5, source=FieldSource.DOCUMENT))


def test_float_income_is_rejected() -> None:
    with pytest.raises(ValidationError):
        IncomeProfile(monthly_net_income=Tracked(value=2_500_000.0, source=FieldSource.DOCUMENT))


# --- 부담률 100% 초과 (실제 채무자 상황) ----------------------------------------


def test_dti_ratio_can_exceed_one_hundred_percent() -> None:
    result = compute(
        (_debt(monthly_payment=Decimal("3000000")),),
        _income(monthly_net_income=Decimal("2000000")),
        _household(),
    )
    assert result.dti_ratio == Decimal("1.500")


# --- trace ---------------------------------------------------------------------


def test_trace_records_every_step() -> None:
    result = compute((_debt(),), _income(), _household())
    labels = [step.label for step in result.trace]
    assert "월 총 예정 상환액" in labels
    assert "월 가용재원" in labels
    assert "월 부족액" in labels
    assert "부담률" in labels


def test_no_dti_step_recorded_when_income_unknown() -> None:
    result = compute((_debt(),), _income(monthly_net_income=None), _household())
    labels = [step.label for step in result.trace]
    assert "부담률" not in labels


# --- Q5_RECENT_DEBT: 실행일이 비어 파생 계산이 안 될 때의 보완입력 ------------------


def _debt_without_executed_at(balance: str) -> Debt:
    return Debt(
        debt_id="no-date",
        balance=Tracked(value=Decimal(balance), source=FieldSource.DOCUMENT),
        executed_at=Tracked(),
    )


def test_recent_debt_ratio_is_unknown_when_executed_at_missing() -> None:
    """실행일이 하나라도 비면 파생 계산은 불가능하다 — 기존 동작."""
    result = compute(
        (_debt_without_executed_at("10000000"),),
        IncomeProfile(),
        HouseholdProfile(),
        as_of=date(2026, 9, 2),
    )
    assert result.recent_debt_ratio is None


def test_declared_no_recent_debt_fills_the_gap() -> None:
    """ "신규채무 없음"(False) 자기신고는 비율 0 의 근거가 된다."""
    result = compute(
        (_debt_without_executed_at("10000000"),),
        IncomeProfile(),
        HouseholdProfile(),
        as_of=date(2026, 9, 2),
        has_recent_debt=False,
    )
    assert result.recent_debt_ratio == Decimal("0")


def test_declared_has_recent_debt_stays_unknown() -> None:
    """ "있다"(True)는 금액을 모르므로 비율을 만들 수 없다.

    자기신고만으로 조건을 충족시키는 방향은 열지 않는다 — 반대 방향만 채운다.
    """
    result = compute(
        (_debt_without_executed_at("10000000"),),
        IncomeProfile(),
        HouseholdProfile(),
        as_of=date(2026, 9, 2),
        has_recent_debt=True,
    )
    assert result.recent_debt_ratio is None


def test_derived_ratio_wins_over_self_report() -> None:
    """실행일이 다 있으면 파생값이 자기신고를 덮는다 — 문서가 자기신고보다 강하다."""
    recent = Debt(
        debt_id="recent",
        balance=Tracked(value=Decimal("10000000"), source=FieldSource.DOCUMENT),
        executed_at=Tracked(value=date(2026, 8, 1), source=FieldSource.DOCUMENT),
    )
    result = compute(
        (recent,),
        IncomeProfile(),
        HouseholdProfile(),
        as_of=date(2026, 9, 2),
        has_recent_debt=False,
    )
    assert result.recent_debt_ratio == Decimal("1")
