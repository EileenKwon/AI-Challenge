"""고도화 — 경계까지의 거리 계산 테스트.

판정이 아니라 순수 산술이라는 것, 값이 없으면(UNKNOWN) 거리를 지어내지
않는다는 것, YAML이 float로 파싱하는 비율값(예: 0.3)도 정확히 처리한다는
것을 검증한다.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from dn.rules.counterfactual import compute_gap, compute_gaps
from dn.rules.policy_card import PolicyCondition


def _cond(op: str, value, field: str = "f", label: str = "l") -> PolicyCondition:
    return PolicyCondition(id="c", label=label, field=field, op=op, value=value, required=True)


# --- 거리 계산 (NOT_MET, 값 확인됨) ----------------------------------------------


def test_gte_gap_increase_direction() -> None:
    condition = _cond("gte", 90, field="max_overdue_days")
    gap = compute_gap(condition, {"max_overdue_days": 77})
    assert gap is not None
    assert gap.gap == Decimal("13")
    assert gap.gap_display == "13일"
    assert gap.direction == "increase"


def test_lte_gap_decrease_direction_money_field() -> None:
    condition = _cond("lte", 1_500_000_000, field="total_debt")
    gap = compute_gap(condition, {"total_debt": Decimal("1_600_000_000")})
    assert gap is not None
    assert gap.gap == Decimal("100000000")
    assert gap.gap_display == "100,000,000원"
    assert gap.direction == "decrease"


def test_lt_gap_handles_yaml_float_value_without_typeerror() -> None:
    """PyYAML은 `0.3`을 float로 파싱한다 — Decimal과의 뺄셈이 TypeError 없이 돼야 한다."""
    condition = _cond("lt", 0.3, field="recent_debt_ratio")
    gap = compute_gap(condition, {"recent_debt_ratio": Decimal("0.35")})
    assert gap is not None
    assert gap.gap == Decimal("0.05")
    assert gap.gap_display == "5.0%p"
    assert gap.direction == "decrease"


def test_between_gap_below_low_and_above_high() -> None:
    condition = _cond("between", [31, 89], field="max_overdue_days")

    below = compute_gap(condition, {"max_overdue_days": 20})
    assert below is not None
    assert below.gap == Decimal("11")
    assert below.direction == "increase"

    above = compute_gap(condition, {"max_overdue_days": 95})
    assert above is not None
    assert above.gap == Decimal("6")
    assert above.direction == "decrease"


# --- 거리 개념이 없는 경우 --------------------------------------------------------


def test_already_met_returns_none() -> None:
    condition = _cond("gte", 90, field="max_overdue_days")
    assert compute_gap(condition, {"max_overdue_days": 90}) is None
    assert compute_gap(condition, {"max_overdue_days": 120}) is None


def test_between_within_range_returns_none() -> None:
    condition = _cond("between", [31, 89], field="max_overdue_days")
    assert compute_gap(condition, {"max_overdue_days": 50}) is None


def test_missing_or_none_value_returns_none_not_a_fabricated_gap() -> None:
    condition = _cond("gte", 90, field="max_overdue_days")
    assert compute_gap(condition, {}) is None
    assert compute_gap(condition, {"max_overdue_days": None}) is None


@pytest.mark.parametrize(
    "op,value",
    [
        ("eq", "x"),
        ("in", ["a", "b"]),
        ("is_true", None),
        ("is_false", None),
        ("exists", None),
    ],
)
def test_non_distance_operators_always_return_none(op, value) -> None:
    condition = _cond(op, value)
    assert compute_gap(condition, {"f": "anything"}) is None
    assert compute_gap(condition, {"f": True}) is None


# --- compute_gaps: 목록 단위 ------------------------------------------------------


def test_compute_gaps_filters_met_and_unknown() -> None:
    conditions = [
        _cond("gte", 90, field="max_overdue_days", label="연체일수 90일 이상"),
        _cond("lte", 500_000_000, field="unsecured_debt", label="무담보 5억 이하"),
        _cond("is_true", None, field="court_proceeding_ongoing", label="회생 진행중 아님"),
    ]
    facts = {
        "max_overdue_days": 77,  # NOT_MET → 거리 있음
        "unsecured_debt": Decimal("300000000"),  # MET → 거리 없음
        # court_proceeding_ongoing 은 아예 미확인
    }
    gaps = compute_gaps(conditions, facts)
    assert len(gaps) == 1
    assert gaps[0].condition_id == "c"
    assert gaps[0].field == "max_overdue_days"
    assert gaps[0].label == "연체일수 90일 이상"
