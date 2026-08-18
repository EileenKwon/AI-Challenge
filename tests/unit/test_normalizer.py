"""T06 — 정규화 테스트."""

from __future__ import annotations

from decimal import Decimal

import pytest

from dn.domain.enums import ProductType
from dn.extraction.normalizer import normalize_field_name, normalize_product_type, parse_money

_FIELD_SYNONYMS = [
    ("대출잔액", "balance"),
    ("채무잔액", "balance"),
    ("원금잔액", "balance"),
    ("미상환원금", "balance"),
    ("대출금 잔액", "balance"),
]

_PRODUCT_TYPE_SAMPLES = [
    ("신용대출", ProductType.CREDIT_LOAN),
    ("카드론", ProductType.CARD_LOAN),
    ("현금서비스", ProductType.CASH_ADVANCE),
    ("할부금융", ProductType.INSTALLMENT),
    ("리볼빙", ProductType.REVOLVING),
    ("담보대출", ProductType.SECURED_LOAN),
]


@pytest.mark.parametrize("raw_label,expected", _FIELD_SYNONYMS)
def test_field_synonyms_normalize_to_balance(raw_label: str, expected: str) -> None:
    assert normalize_field_name(raw_label) == expected


def test_field_synonym_count_is_at_least_five() -> None:
    assert len(_FIELD_SYNONYMS) >= 5


def test_unknown_field_label_returns_none() -> None:
    assert normalize_field_name("전혀 모르는 라벨") is None


@pytest.mark.parametrize("raw_type,expected", _PRODUCT_TYPE_SAMPLES)
def test_product_type_synonyms_normalize(raw_type: str, expected: ProductType) -> None:
    assert normalize_product_type(raw_type) == expected


def test_product_type_sample_count_is_at_least_six() -> None:
    assert len(_PRODUCT_TYPE_SAMPLES) >= 6


def test_unknown_product_type_becomes_other() -> None:
    assert normalize_product_type("전혀 새로운 상품") == ProductType.OTHER


def test_missing_product_type_stays_none() -> None:
    assert normalize_product_type(None) is None
    assert normalize_product_type("") is None


def test_parse_money_handles_comma_won_format() -> None:
    assert parse_money("25,000,000원") == Decimal("25000000")


def test_parse_money_handles_plain_digits() -> None:
    assert parse_money("7000000") == Decimal("7000000")


def test_parse_money_handles_man_won_format() -> None:
    assert parse_money("2500만원") == Decimal("25000000")
    assert parse_money("2500만") == Decimal("25000000")


def test_parse_money_returns_none_for_garbage() -> None:
    assert parse_money("모름") is None
    assert parse_money("") is None
    assert parse_money(None) is None
