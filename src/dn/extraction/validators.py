"""추출된 채무 목록의 형식·합계 검증과 confidence 산출.

confidence = 원문 매칭 여부 + 형식 유효성 + 합계 정합성을 규칙 기반으로 결합한다.
LLM 이 자기보고한 확신도는 사용하지 않는다 (T06 세부 규칙).
"""

from __future__ import annotations

from decimal import Decimal

from dn.domain.models import Debt

_BASE_CONFIDENCE = Decimal("0.9")
_SUM_MISMATCH_PENALTY = Decimal("0.3")
_FORMAT_INVALID_PENALTY = Decimal("0.4")
_NOT_MATCHED_PENALTY = Decimal("0.2")
_SUM_TOLERANCE = Decimal("1")  # 원 단위 반올림 오차 허용


def compute_balance_confidence(
    debt: Debt,
    *,
    matched_in_source: bool,
    sum_consistent: bool,
) -> Decimal:
    """단일 채무의 잔액 confidence 를 규칙 기반으로 산출한다."""
    score = _BASE_CONFIDENCE
    if debt.balance.value is None:
        score -= _FORMAT_INVALID_PENALTY
    if not matched_in_source:
        score -= _NOT_MATCHED_PENALTY
    if not sum_consistent:
        score -= _SUM_MISMATCH_PENALTY
    return max(score, Decimal("0"))


def validate_debts(
    debts: tuple[Debt, ...], *, doc_total_balance: Decimal | None
) -> tuple[Debt, ...]:
    """잔액 합계를 문서 총액과 대조하고, 불일치 시 confidence 를 낮춘 사본을 반환한다."""
    known_balances = [d.balance.value for d in debts if d.balance.value is not None]
    computed_sum = sum(known_balances, Decimal("0"))

    sum_consistent = True
    if doc_total_balance is not None and known_balances:
        sum_consistent = abs(computed_sum - doc_total_balance) <= _SUM_TOLERANCE

    updated: list[Debt] = []
    for debt in debts:
        matched_in_source = debt.balance.raw_text is not None
        new_confidence = compute_balance_confidence(
            debt, matched_in_source=matched_in_source, sum_consistent=sum_consistent
        )
        updated_balance = debt.balance.model_copy(update={"confidence": new_confidence})
        updated.append(debt.model_copy(update={"balance": updated_balance}))
    return tuple(updated)
