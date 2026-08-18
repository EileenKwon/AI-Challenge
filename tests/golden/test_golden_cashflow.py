"""T08 — 골든 케이스 기반 현금흐름 계산 정확성 검증 (오차 0 요구사항).

기획서 15장 김하늘 사례를 포함해 최소 5건의 경계값 케이스를 검증한다:
부족액 0, 음수(여유), 전 항목 결측, 일부 결측, 기본 사례.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml

from dn.cashflow.calculator import compute
from dn.domain.enums import FieldSource, ProductType
from dn.domain.models import Debt, HouseholdProfile, IncomeProfile
from dn.domain.provenance import Tracked

_GOLDEN_DIR = Path(__file__).resolve().parent

_GOLDEN_FILES = [
    "kimhaneul.yaml",
    "shortfall_zero.yaml",
    "shortfall_negative_surplus.yaml",
    "all_fields_missing.yaml",
    "partial_payment_missing.yaml",
]


def _tracked(value: Any) -> Tracked:
    if value is None:
        return Tracked()
    return Tracked(value=value, source=FieldSource.DOCUMENT)


def _money(raw: dict[str, Any], key: str) -> Decimal | None:
    return Decimal(str(raw[key])) if key in raw else None


def _debt_from_yaml(raw: dict[str, Any], index: int) -> Debt:
    product_type = ProductType(raw["product_type"]) if raw.get("product_type") else None
    return Debt(
        debt_id=f"d{index}",
        creditor=_tracked(raw.get("creditor")),
        product_type=_tracked(product_type),
        balance=_tracked(_money(raw, "balance")),
        overdue_days=_tracked(raw.get("overdue_days")),
        is_secured=_tracked(raw.get("is_secured")),
        monthly_payment=_tracked(_money(raw, "monthly_payment")),
    )


def _income_from_yaml(raw: dict[str, Any]) -> IncomeProfile:
    return IncomeProfile(
        monthly_net_income=_tracked(_money(raw, "monthly_net_income")),
        support_income=_tracked(_money(raw, "support_income")),
    )


def _household_from_yaml(raw: dict[str, Any]) -> HouseholdProfile:
    return HouseholdProfile(
        essential_living_cost=_tracked(_money(raw, "essential_living_cost")),
        housing_cost=_tracked(_money(raw, "housing_cost")),
        medical_care_cost=_tracked(_money(raw, "medical_care_cost")),
        other_fixed_cost=_tracked(_money(raw, "other_fixed_cost")),
        dependents=_tracked(raw.get("dependents")),
    )


def _load_case(filename: str) -> dict[str, Any]:
    return yaml.safe_load((_GOLDEN_DIR / filename).read_text(encoding="utf-8"))


@pytest.mark.parametrize("filename", _GOLDEN_FILES)
def test_golden_case_matches_expected_exactly(filename: str) -> None:
    case = _load_case(filename)
    debts = tuple(_debt_from_yaml(d, i) for i, d in enumerate(case["input"]["debts"]))
    income = _income_from_yaml(case["input"].get("income") or {})
    household = _household_from_yaml(case["input"].get("household") or {})

    result = compute(debts, income, household)
    expected = case["expected"]
    case_id = case["id"]

    assert result.total_debt == Decimal(str(expected["total_debt"])), case_id
    assert result.monthly_total_payment == Decimal(str(expected["monthly_total_payment"])), case_id
    assert result.monthly_available == Decimal(str(expected["monthly_available"])), case_id
    assert result.monthly_shortfall == Decimal(str(expected["monthly_shortfall"])), case_id

    if expected.get("dti_ratio") is None:
        assert result.dti_ratio is None, case_id
    else:
        assert result.dti_ratio == Decimal(expected["dti_ratio"]), case_id

    if expected.get("max_overdue_days") is None:
        assert result.max_overdue_days is None, case_id
    else:
        assert result.max_overdue_days == expected["max_overdue_days"], case_id

    if "excluded_items" in expected:
        assert list(result.excluded_items) == expected["excluded_items"], case_id
    if "excluded_items_count" in expected:
        assert len(result.excluded_items) == expected["excluded_items_count"], case_id


def test_at_least_five_golden_cases_exist() -> None:
    assert len(_GOLDEN_FILES) >= 5
    for filename in _GOLDEN_FILES:
        assert (_GOLDEN_DIR / filename).exists()
