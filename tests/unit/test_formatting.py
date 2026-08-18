"""T08 — 표시용 포맷터 테스트."""

from __future__ import annotations

from decimal import Decimal

from dn.cashflow.formatting import format_ratio, format_won


def test_format_won_man_unit() -> None:
    assert format_won(Decimal("46000000")) == "4,600만 원"


def test_format_won_matches_kimhaneul_narrative_values() -> None:
    assert format_won(Decimal("1050000")) == "105만 원"
    assert format_won(Decimal("1180000")) == "118만 원"
    assert format_won(Decimal("130000")) == "13만 원"


def test_format_won_handles_negative() -> None:
    assert format_won(Decimal("-700000")) == "-70만 원"


def test_format_won_handles_zero() -> None:
    assert format_won(Decimal("0")) == "0 원"


def test_format_won_handles_none() -> None:
    assert format_won(None) == "확인되지 않음"


def test_format_won_handles_eok_unit() -> None:
    assert format_won(Decimal("150000000")) == "1억 5,000만 원"


def test_format_ratio_matches_kimhaneul_narrative() -> None:
    assert format_ratio(Decimal("0.472")) == "47.2%"


def test_format_ratio_handles_none() -> None:
    assert format_ratio(None) == "확인되지 않음"


def test_format_ratio_can_exceed_one_hundred_percent() -> None:
    assert format_ratio(Decimal("1.5")) == "150.0%"
