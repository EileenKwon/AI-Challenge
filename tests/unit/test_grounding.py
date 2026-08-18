"""T14 — 숫자 그라운딩 검증 테스트.

표기 변형 6종 이상을 정상 인식하는지, 허용 집합에 없는 숫자가 하나라도
있으면 실패 판정하는지 검증한다.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from dn.narrative.grounding import extract_number_tokens, validate_grounding

_ALLOWED = frozenset(
    {
        Decimal("46000000"),
        Decimal("130000"),
        Decimal("1050000"),
        Decimal("1180000"),
        Decimal("0.472"),
        Decimal("42"),
        Decimal("150000000"),
    }
)


# --- 표기 변형 6종 이상 --------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected_value",
    [
        ("총 채무액은 46,000,000원입니다.", Decimal("46000000")),
        ("총 채무액은 4,600만원입니다.", Decimal("46000000")),
        ("총 채무액은 4,600만 원입니다.", Decimal("46000000")),
        ("총 채무액은 4600만원입니다.", Decimal("46000000")),
        ("매달 13만 원이 부족합니다.", Decimal("130000")),
        ("소득의 47.2%가 상환에 들어갑니다.", Decimal("0.472")),
        ("연체일수는 42일입니다.", Decimal("42")),
        ("총 채무액은 1억 5,000만원입니다.", Decimal("150000000")),
    ],
)
def test_notation_variants_are_recognized_and_grounded(text: str, expected_value: Decimal) -> None:
    tokens = extract_number_tokens(text)
    values = [v for _, v in tokens]
    assert expected_value in values

    report = validate_grounding(text, _ALLOWED)
    assert report.grounded is True, report.ungrounded_tokens


def test_at_least_six_notation_variants_covered() -> None:
    variants = [
        "46,000,000원",
        "4,600만원",
        "4,600만 원",
        "4600만원",
        "13만 원",
        "47.2%",
    ]
    assert len(variants) >= 6
    for v in variants:
        assert extract_number_tokens(v), f"인식 실패: {v}"


# --- 허용 집합에 없는 숫자 1개 삽입 시 실패 -------------------------------------


def test_ungrounded_number_fails_validation() -> None:
    text = "매달 13만 원이 부족하며, 대출한도는 9,999만원입니다."
    report = validate_grounding(text, _ALLOWED)
    assert report.grounded is False
    assert any("9,999만원" in token for token in report.ungrounded_tokens)


def test_fully_grounded_text_passes() -> None:
    text = "매달 13만 원이 부족합니다. 연체일수는 42일이며 소득의 47.2%가 상환에 들어갑니다."
    report = validate_grounding(text, _ALLOWED)
    assert report.grounded is True
    assert report.ungrounded_tokens == ()


def test_negative_shortfall_is_recognized() -> None:
    allowed = frozenset({Decimal("-700000")})
    report = validate_grounding("이번 달은 -700,000원의 여유가 있습니다.", allowed)
    assert report.grounded is True


def test_ordinal_like_number_outside_allowed_set_fails() -> None:
    text = "채무는 총 3건이며, 그중 999건이 연체입니다."
    report = validate_grounding(text, frozenset({Decimal("3")}))
    assert report.grounded is False
