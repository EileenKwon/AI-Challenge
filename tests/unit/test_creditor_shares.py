"""화면 05 "금융회사별 채무 현황" 집계(`_creditor_shares`) 테스트.

2026-09-06 리포트: 특정 채권자 1개가 100%로 표시되는 사례가 있었다. 원인은
`if debt.balance.value` 같은 truthy 검사가 잔액 0원인 채무를 "미확인"과 함께
걸러내던 것 — 0은 유효하게 확인된 값이라 제외하면 안 된다. 이 파일은 그
회귀와, 동일 채권자 여러 건 합산, 반올림 오차를 검증한다.
"""

from __future__ import annotations

from decimal import Decimal

from dn.domain.enums import FieldSource
from dn.domain.models import Debt, ExtractionResult
from dn.domain.provenance import Tracked
from dn.web.routes import _creditor_shares


def _debt(debt_id: str, creditor: str | None, balance: Decimal | None) -> Debt:
    def tracked(value):
        if value is None:
            return Tracked()
        return Tracked(value=value, source=FieldSource.DOCUMENT)

    return Debt(debt_id=debt_id, creditor=tracked(creditor), balance=tracked(balance))


def test_single_debt_gets_100_percent() -> None:
    extraction = ExtractionResult(debts=(_debt("d0", "OO캐피탈", Decimal("5000000")),))
    shares, excluded = _creditor_shares(extraction)
    assert excluded == 0
    assert shares == [{"creditor": "OO캐피탈", "balance": "500만 원", "percent": 100}]


def test_two_debts_different_creditors_split_by_balance() -> None:
    extraction = ExtractionResult(
        debts=(
            _debt("d0", "OO캐피탈", Decimal("6000000")),
            _debt("d1", "XX카드", Decimal("4000000")),
        )
    )
    shares, excluded = _creditor_shares(extraction)
    assert excluded == 0
    percents = {row["creditor"]: row["percent"] for row in shares}
    assert percents == {"OO캐피탈": 60, "XX카드": 40}


def test_three_debts_percentages_sum_within_rounding_tolerance() -> None:
    """반올림 오차 범위 내 100% — 각 항목을 독립적으로 반올림하면 99~101%가 될 수 있다."""
    extraction = ExtractionResult(
        debts=(
            _debt("d0", "가나캐피탈", Decimal("1")),
            _debt("d1", "다라파이낸스", Decimal("1")),
            _debt("d2", "마바캐피탈", Decimal("1")),
        )
    )
    shares, excluded = _creditor_shares(extraction)
    assert excluded == 0
    assert len(shares) == 3
    total_percent = sum(row["percent"] for row in shares)
    assert abs(total_percent - 100) <= 2, f"반올림 오차 범위를 벗어남: {total_percent}%"


def test_same_creditor_multiple_debts_are_grouped_into_one_row() -> None:
    """동일 채권자 채무 여러 건 — 별도 행이 아니라 잔액을 합산한 한 행으로 묶인다."""
    extraction = ExtractionResult(
        debts=(
            _debt("d0", "OO캐피탈", Decimal("3000000")),
            _debt("d1", "OO캐피탈", Decimal("2000000")),
            _debt("d2", "XX카드", Decimal("5000000")),
        )
    )
    shares, excluded = _creditor_shares(extraction)
    assert excluded == 0
    assert len(shares) == 2, "같은 채권자가 별도 행으로 중복되면 안 된다"
    by_creditor = {row["creditor"]: row for row in shares}
    assert by_creditor["OO캐피탈"]["percent"] == 50
    assert by_creditor["OO캐피탈"]["balance"] == "500만 원"
    assert by_creditor["XX카드"]["percent"] == 50


def test_zero_balance_debt_is_not_dropped_and_does_not_inflate_others_to_100_percent() -> None:
    """회귀 테스트 — 잔액 0원인 채무가 truthy 검사로 걸러져 다른 채권자가 100%가 되면 안 된다."""
    extraction = ExtractionResult(
        debts=(
            _debt("d0", "OO캐피탈", Decimal("5000000")),
            _debt("d1", "다갚은카드", Decimal("0")),
        )
    )
    shares, excluded = _creditor_shares(extraction)
    assert excluded == 0, "잔액 0원은 미확인이 아니라 확인된 값이므로 제외되면 안 된다"
    assert len(shares) == 2
    percents = {row["creditor"]: row["percent"] for row in shares}
    assert percents == {"OO캐피탈": 100, "다갚은카드": 0}


def test_missing_balance_debt_is_excluded_from_both_numerator_and_denominator() -> None:
    """잔액이 아예 미확인(None)인 채무는 집계에서 빠지고 건수만 알려준다."""
    extraction = ExtractionResult(
        debts=(
            _debt("d0", "OO캐피탈", Decimal("5000000")),
            _debt("d1", "잔액모름캐피탈", None),
        )
    )
    shares, excluded = _creditor_shares(extraction)
    assert excluded == 1
    assert shares == [{"creditor": "OO캐피탈", "balance": "500만 원", "percent": 100}]


def test_all_debts_missing_balance_returns_empty_with_full_excluded_count() -> None:
    extraction = ExtractionResult(debts=(_debt("d0", "OO캐피탈", None),))
    shares, excluded = _creditor_shares(extraction)
    assert shares == []
    assert excluded == 1


def test_no_debts_returns_empty() -> None:
    shares, excluded = _creditor_shares(ExtractionResult())
    assert shares == []
    assert excluded == 0


def test_missing_creditor_name_falls_back_to_placeholder_not_dropped() -> None:
    extraction = ExtractionResult(debts=(_debt("d0", None, Decimal("1000000")),))
    shares, excluded = _creditor_shares(extraction)
    assert excluded == 0
    assert shares == [{"creditor": "미확인 채권자", "balance": "100만 원", "percent": 100}]
