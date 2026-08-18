"""T04 — PII 마스킹 테스트."""

from __future__ import annotations

import pytest

from dn.ingest.pii_masker import mask

_PII_SAMPLES: list[tuple[str, str]] = [
    ("900101-1234567", "rrn"),
    ("991231-2234567", "rrn"),
    ("110-123-456789", "account"),
    ("356-0123-45678", "account"),
    ("1002-345-678901", "account"),
    ("1234-5678-9012-3456", "card"),
    ("1234 5678 9012 3456", "card"),
    ("010-1234-5678", "phone"),
    ("02-123-4567", "phone"),
    ("user@example.com", "email"),
]


@pytest.mark.parametrize("raw,kind", _PII_SAMPLES)
def test_pii_shaped_strings_are_masked(raw: str, kind: str) -> None:
    text = f"고객 정보: {raw} 확인 요망"
    masked_text, report = mask(text)
    assert raw not in masked_text
    assert report.masked_counts.get(kind, 0) >= 1


def test_all_ten_samples_are_distinct_shapes() -> None:
    assert len({raw for raw, _ in _PII_SAMPLES}) == 10


def test_address_dong_ho_is_masked() -> None:
    masked_text, report = mask("거주지: 456동 789호")
    assert "456동 789호" not in masked_text
    assert report.masked_counts.get("address", 0) == 1


def test_amounts_are_not_masked() -> None:
    text = "총 채무액은 46,000,000원이며 월 상환액은 1,180,000원입니다."
    masked_text, report = mask(text)
    assert masked_text == text
    assert report.total == 0


def test_dates_are_not_masked() -> None:
    text = "정책 기준일은 2026-08-13이며 실행일은 2024-11-02입니다."
    masked_text, report = mask(text)
    assert masked_text == text
    assert report.total == 0


def test_creditor_company_names_are_not_masked() -> None:
    text = "A금융, B카드, C캐피탈, 신한은행, 우리카드에서 채무가 확인되었습니다."
    masked_text, report = mask(text)
    assert masked_text == text
    assert report.total == 0


def test_text_without_pii_is_unchanged() -> None:
    text = "이 문서에는 개인정보가 없습니다."
    masked_text, report = mask(text)
    assert masked_text == text
    assert report.total == 0
