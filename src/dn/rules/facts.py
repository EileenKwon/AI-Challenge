"""규칙 엔진 입력용 사실(facts) 딕셔너리 조립.

`Debt[]`, `IncomeProfile`, `CashflowResult`, `SituationFlags` 로부터 정책
카드 조건이 참조하는 필드명과 일치하는 평면 딕셔너리를 만든다.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from dn.domain.models import CashflowResult, Debt, IncomeProfile, SituationFlags
from dn.reconcile.questions import has_income_drop_signal, has_overdue, has_secured_debt


def _split_by_collateral(debts: tuple[Debt, ...]) -> tuple[Decimal | None, Decimal | None]:
    """담보/무담보 잔액 합계.

    신용회복위원회 제도는 총 채무액 한도를 담보·무담보로 나눠 규정한다
    (예: 총 15억원 이하 = 무담보 5억원 + 담보 10억원). 따라서 총액만으로는
    한도 조건을 평가할 수 없다.

    잔액 또는 담보 여부가 하나라도 미확인이면 합계를 신뢰할 수 없으므로
    `None` 을 돌려준다 — 평가기가 이를 UNKNOWN 으로 받아 "모른다"를 유지한다.
    """
    if not debts:
        return None, None
    secured = Decimal("0")
    unsecured = Decimal("0")
    for d in debts:
        balance = d.balance.value
        is_secured = d.is_secured.value
        if balance is None or is_secured is None:
            return None, None
        if is_secured:
            secured += balance
        else:
            unsecured += balance
    return secured, unsecured


def build_facts(
    debts: tuple[Debt, ...],
    income: IncomeProfile,
    cashflow: CashflowResult,
    flags: SituationFlags,
) -> dict[str, Any]:
    """정책 카드 조건이 참조하는 필드명(예: `max_overdue_days`)으로 사실을 조립한다."""
    secured_debt, unsecured_debt = _split_by_collateral(debts)
    return {
        "max_overdue_days": cashflow.max_overdue_days,
        "total_debt": cashflow.total_debt,
        # 담보/무담보 한도를 따로 규정하는 제도가 있어 총액과 별도로 노출한다.
        "secured_debt": secured_debt,
        "unsecured_debt": unsecured_debt,
        # 최근 6개월 신규채무 원금 비율 — 신복위 제도 공통 조건(30% 미만).
        "recent_debt_ratio": cashflow.recent_debt_ratio,
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
