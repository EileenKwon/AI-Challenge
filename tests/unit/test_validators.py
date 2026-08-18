"""T06 — 검증·confidence 산출 테스트."""

from __future__ import annotations

from decimal import Decimal

from dn.domain.enums import FieldSource
from dn.domain.models import Debt
from dn.domain.provenance import Tracked
from dn.extraction.validators import compute_balance_confidence, validate_debts


def _debt(balance: Decimal | None, *, matched_raw_text: str | None) -> Debt:
    return Debt(
        debt_id="d0",
        balance=Tracked(value=balance, source=FieldSource.DOCUMENT, raw_text=matched_raw_text),
    )


def test_confidence_drops_when_sum_mismatches_document_total() -> None:
    debts = (
        _debt(Decimal("10000000"), matched_raw_text="10,000,000원"),
        _debt(Decimal("5000000"), matched_raw_text="5,000,000원"),
    )
    consistent = validate_debts(debts, doc_total_balance=Decimal("15000000"))
    inconsistent = validate_debts(debts, doc_total_balance=Decimal("99000000"))

    assert consistent[0].balance.confidence > inconsistent[0].balance.confidence
    assert consistent[1].balance.confidence > inconsistent[1].balance.confidence


def test_confidence_is_none_penalized_further_for_missing_value() -> None:
    debts = (_debt(None, matched_raw_text=None),)
    result = validate_debts(debts, doc_total_balance=None)
    known_debt = _debt(Decimal("1000000"), matched_raw_text="1,000,000원")
    known_result = validate_debts((known_debt,), doc_total_balance=None)

    assert result[0].balance.confidence < known_result[0].balance.confidence


def test_compute_balance_confidence_penalizes_each_failure_independently() -> None:
    debt = _debt(Decimal("1000000"), matched_raw_text="1,000,000원")
    full = compute_balance_confidence(debt, matched_in_source=True, sum_consistent=True)
    no_match = compute_balance_confidence(debt, matched_in_source=False, sum_consistent=True)
    no_sum = compute_balance_confidence(debt, matched_in_source=True, sum_consistent=False)

    assert full > no_match
    assert full > no_sum


def test_confidence_never_goes_below_zero() -> None:
    debt = _debt(None, matched_raw_text=None)
    score = compute_balance_confidence(debt, matched_in_source=False, sum_consistent=False)
    assert score >= Decimal("0")


def test_no_document_total_skips_sum_check() -> None:
    debts = (_debt(Decimal("1000000"), matched_raw_text="1,000,000원"),)
    result = validate_debts(debts, doc_total_balance=None)
    assert result[0].balance.confidence == compute_balance_confidence(
        debts[0], matched_in_source=True, sum_consistent=True
    )
