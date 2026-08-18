"""T06 — 추출기 테스트."""

from __future__ import annotations

import json

from dn.domain.enums import ProductType
from dn.domain.models import DocumentContent, PageContent
from dn.extraction.extractor import extract
from dn.llm.client import StubClient

_FIXED_RESPONSE = json.dumps(
    {
        "debts": [
            {
                "creditor": "A금융",
                "product_type": "신용대출",
                "balance": "25,000,000원",
                "executed_at": "2023-05-01",
                "overdue_days": 42,
                "is_secured": False,
            },
            {
                "creditor": "B카드",
                "product_type": "카드론",
                "balance": "14,000,000원",
                "executed_at": "2022-01-10",
                "overdue_days": 0,
                "is_secured": False,
            },
            {
                "creditor": "C캐피탈",
                "product_type": None,
                "balance": None,
                "executed_at": None,
                "overdue_days": None,
                "is_secured": None,
            },
        ]
    }
)


def _document() -> DocumentContent:
    return DocumentContent(
        doc_id="doc-1",
        filename="report.pdf",
        is_scanned=False,
        pages=(PageContent(page_no=1, text="신용정보조회서 내용 A금융 B카드 C캐피탈"),),
    )


def test_extract_produces_exactly_three_debts() -> None:
    client = StubClient(response=_FIXED_RESPONSE)
    debts = extract(_document(), client=client)
    assert len(debts) == 3


def test_extract_maps_known_fields_correctly() -> None:
    client = StubClient(response=_FIXED_RESPONSE)
    debts = extract(_document(), client=client)

    first = debts[0]
    assert first.creditor.value == "A금융"
    assert first.product_type.value == ProductType.CREDIT_LOAN
    assert first.balance.value == 25_000_000
    assert first.overdue_days.value == 42
    assert first.is_secured.value is False


def test_extract_preserves_missing_fields_as_none() -> None:
    client = StubClient(response=_FIXED_RESPONSE)
    debts = extract(_document(), client=client)

    third = debts[2]
    assert third.creditor.value == "C캐피탈"
    assert third.product_type.value is None
    assert third.balance.value is None
    assert third.overdue_days.value is None


def test_extract_does_not_populate_interest_rate_or_payment_fields() -> None:
    client = StubClient(response=_FIXED_RESPONSE)
    debts = extract(_document(), client=client)
    for debt in debts:
        assert debt.interest_rate.value is None
        assert debt.monthly_payment.value is None
        assert debt.repayment_type.value is None


def test_all_extracted_fields_have_document_source() -> None:
    client = StubClient(response=_FIXED_RESPONSE)
    debts = extract(_document(), client=client)
    for debt in debts:
        assert debt.creditor.source.value == "document"
        assert debt.product_type.source.value == "document"
        assert debt.balance.source.value == "document"
