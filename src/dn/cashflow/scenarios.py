"""소득 감소 시나리오 분석 (기획서 5.2 축소 구현: 소득 20% 감소 단일 시나리오).

별도 계산 로직을 두지 않는다. 소득 필드만 치환해 `calculator.compute()` 를
재호출한다.
"""

from __future__ import annotations

from decimal import Decimal

from dn.cashflow.calculator import compute
from dn.domain.models import Debt, HouseholdProfile, IncomeProfile, ScenarioResult

_DEFAULT_RATIO = Decimal("0.2")


def income_drop(
    debts: tuple[Debt, ...],
    income: IncomeProfile,
    household: HouseholdProfile,
    *,
    ratio: Decimal = _DEFAULT_RATIO,
) -> ScenarioResult:
    """소득이 `ratio` 만큼 줄었다면 현금흐름이 어떻게 바뀌는지 계산한다."""
    before = compute(debts, income, household)

    reduced_value = None
    if income.monthly_net_income.value is not None:
        factor = Decimal("1") - ratio
        reduced_value = (income.monthly_net_income.value * factor).to_integral_value()
    reduced_tracked = income.monthly_net_income.model_copy(update={"value": reduced_value})
    reduced_income = income.model_copy(update={"monthly_net_income": reduced_tracked})

    after = compute(debts, reduced_income, household)

    percent = int((ratio * Decimal("100")).to_integral_value())
    return ScenarioResult(
        scenario_id=f"income_drop_{percent}",
        label=f"소득이 {percent}% 줄어든다면",
        before=before,
        after=after,
    )
