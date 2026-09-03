"""T08 — 표시용 포맷터 테스트."""

from __future__ import annotations

from decimal import Decimal

from dn.cashflow.formatting import format_ratio, format_ratio_plain, format_won


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


# --- 쉬운 말 모드 -----------------------------------------------------------------


def test_format_ratio_plain_handles_none() -> None:
    assert format_ratio_plain(None) == "확인되지 않음"


def test_format_ratio_plain_matches_kimhaneul_example() -> None:
    """기획서 데모 사례(부담률 47.2%)와 같은 구간(0.3~0.5)의 문구를 확인한다."""
    assert format_ratio_plain(Decimal("0.472")) == "버는 돈의 절반 가까이가 빚 갚는 데 들어갑니다"


def test_format_ratio_plain_buckets_are_ordered_and_exhaustive() -> None:
    assert format_ratio_plain(Decimal("0.05")) == "버는 돈에 비해 빚 갚는 부담이 크지 않습니다"
    assert format_ratio_plain(Decimal("0.2")) == "버는 돈의 일부가 빚 갚는 데 들어갑니다"
    assert format_ratio_plain(Decimal("0.6")) == "버는 돈의 절반 이상이 빚 갚는 데 들어갑니다"
    assert format_ratio_plain(Decimal("0.9")) == "버는 돈의 대부분이 빚 갚는 데 들어갑니다"


def test_format_ratio_plain_handles_overflow_above_one() -> None:
    assert format_ratio_plain(Decimal("1.5")) == "벌어들이는 돈보다 갚아야 할 돈이 더 많습니다"


def test_format_ratio_plain_boundary_values_use_upper_bucket() -> None:
    """경계값은 다음(더 부담이 큰) 구간에 속한다 — `< threshold` 비교이므로."""
    assert format_ratio_plain(Decimal("0.3")) == "버는 돈의 절반 가까이가 빚 갚는 데 들어갑니다"
    assert format_ratio_plain(Decimal("1.0")) == "벌어들이는 돈보다 갚아야 할 돈이 더 많습니다"
