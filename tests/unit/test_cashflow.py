"""T08 — 현금흐름 계산 단위 테스트: 결측 3종 시나리오, 소득 0, float 입력 거부."""

from __future__ import annotations

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
