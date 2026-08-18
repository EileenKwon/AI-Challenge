"""T01 — 도메인 모델 계약 테스트."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from dn.domain.enums import FieldSource
from dn.domain.models import CashflowResult, Debt
from dn.domain.provenance import Money, Ratio, Tracked


class _MoneyHolder(BaseModel):
    model_config = ConfigDict(frozen=True)
    amount: Money


class _RatioHolder(BaseModel):
    model_config = ConfigDict(frozen=True)
    ratio: Ratio


def test_money_rejects_float() -> None:
    with pytest.raises(ValidationError):
        _MoneyHolder(amount=1_000_000.5)


def test_money_rejects_non_integral_decimal() -> None:
    with pytest.raises(ValidationError):
        _MoneyHolder(amount=Decimal("1000.5"))


def test_money_accepts_int_and_decimal() -> None:
    assert _MoneyHolder(amount=1_000_000).amount == Decimal("1000000")
    assert _MoneyHolder(amount=Decimal("2000000")).amount == Decimal("2000000")


def test_ratio_rejects_out_of_range() -> None:
    with pytest.raises(ValidationError):
        _RatioHolder(ratio=Decimal("1.5"))
    with pytest.raises(ValidationError):
        _RatioHolder(ratio=Decimal("-0.1"))


def test_ratio_rejects_float() -> None:
    with pytest.raises(ValidationError):
        _RatioHolder(ratio=0.5)


def test_tracked_unknown_value_is_not_known() -> None:
    t: Tracked[Decimal] = Tracked(value=None)
    assert t.is_known is False
    assert t.source == FieldSource.UNKNOWN


def test_tracked_known_value_is_known() -> None:
    t: Tracked[Decimal] = Tracked(value=Decimal("100"), source=FieldSource.USER_INPUT)
    assert t.is_known is True


def test_debt_balance_rejects_float_via_tracked() -> None:
    with pytest.raises(ValidationError):
        Debt(debt_id="d0", balance=Tracked(value=100.5, source=FieldSource.DOCUMENT))


def test_all_models_round_trip_model_dump_json() -> None:
    debt = Debt(
        debt_id="d0",
        balance=Tracked(value=Decimal("1000000"), source=FieldSource.DOCUMENT),
    )
    dumped = debt.model_dump_json()
    restored = Debt.model_validate_json(dumped)
    assert restored == debt

    cashflow = CashflowResult(
        total_debt=Decimal("46000000"),
        monthly_total_payment=Decimal("1180000"),
        monthly_available=Decimal("1050000"),
        monthly_shortfall=Decimal("130000"),
        dti_ratio=Decimal("0.472"),
    )
    dumped_cf = cashflow.model_dump_json()
    restored_cf = CashflowResult.model_validate_json(dumped_cf)
    assert restored_cf == cashflow


def test_models_are_frozen() -> None:
    debt = Debt(debt_id="d0")
    with pytest.raises(ValidationError):
        debt.debt_id = "d1"  # type: ignore[misc]
