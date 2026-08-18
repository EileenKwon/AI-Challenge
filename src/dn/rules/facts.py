"""규칙 엔진 입력용 사실(facts) 딕셔너리 조립.

`Debt[]`, `IncomeProfile`, `CashflowResult`, `SituationFlags` 로부터 정책
카드 조건이 참조하는 필드명과 일치하는 평면 딕셔너리를 만든다.
"""

from __future__ import annotations

from typing import Any

from dn.domain.models import CashflowResult, Debt, IncomeProfile, SituationFlags
from dn.reconcile.questions import has_income_drop_signal, has_overdue, has_secured_debt


def build_facts(
    debts: tuple[Debt, ...],
    income: IncomeProfile,
    cashflow: CashflowResult,
    flags: SituationFlags,
) -> dict[str, Any]:
    """정책 카드 조건이 참조하는 필드명(예: `max_overdue_days`)으로 사실을 조립한다."""
    return {
        "max_overdue_days": cashflow.max_overdue_days,
        "total_debt": cashflow.total_debt,
        "has_continuous_income": income.has_continuous_income.value,
        "income_proof_available": income.income_proof_available.value,
        "has_secured_debt": has_secured_debt(debts),
        "has_overdue": has_overdue(debts),
        "income_drop_signal": has_income_drop_signal(flags),
        "court_proceeding_ongoing": flags.court_proceeding_ongoing.value,
        "seizure_ongoing": flags.seizure_ongoing.value,
        "has_guarantee_debt": flags.has_guarantee_debt.value,
        "has_tax_debt": flags.has_tax_debt.value,
        "has_private_debt": flags.has_private_debt.value,
        "legal_dispute": flags.legal_dispute.value,
        # T13 트리아지의 "상환여력 사실상 없음" 신호에 쓰인다.
        "monthly_available": cashflow.monthly_available,
    }
