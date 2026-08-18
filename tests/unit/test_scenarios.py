"""T09 — 소득 감소 시나리오 테스트. 기획서 15장 김하늘 사례로 검증한다."""

from __future__ import annotations

from decimal import Decimal

from dn.cashflow.scenarios import income_drop
from dn.domain.enums import FieldSource, ProductType
from dn.domain.models import Debt, HouseholdProfile, IncomeProfile
from dn.domain.provenance import Tracked


def _known(value):
    return Tracked(value=value, source=FieldSource.DOCUMENT)


def _kimhaneul_inputs():
    debts = (
        Debt(
            debt_id="d0",
            creditor=_known("A금융"),
            product_type=_known(ProductType.CREDIT_LOAN),
            balance=_known(Decimal("25000000")),
            overdue_days=_known(42),
            is_secured=_known(False),
            monthly_payment=_known(Decimal("620000")),
        ),
        Debt(
            debt_id="d1",
            creditor=_known("B카드"),
            product_type=_known(ProductType.CARD_LOAN),
            balance=_known(Decimal("14000000")),
            overdue_days=_known(0),
            is_secured=_known(False),
            monthly_payment=_known(Decimal("380000")),
        ),
        Debt(
            debt_id="d2",
            creditor=_known("C캐피탈"),
            product_type=_known(ProductType.CREDIT_LOAN),
            balance=_known(Decimal("7000000")),
            overdue_days=_known(0),
            is_secured=_known(False),
            monthly_payment=_known(Decimal("180000")),
        ),
    )
    income = IncomeProfile(monthly_net_income=_known(Decimal("2500000")), support_income=_known(0))
    household = HouseholdProfile(
        essential_living_cost=_known(Decimal("1450000")),
        housing_cost=_known(0),
        medical_care_cost=_known(0),
        other_fixed_cost=_known(0),
        dependents=_known(0),
    )
    return debts, income, household


def test_kimhaneul_income_drop_20_percent() -> None:
    debts, income, household = _kimhaneul_inputs()
    scenario = income_drop(debts, income, household)

    assert scenario.before.monthly_available == Decimal("1050000")
    assert scenario.before.monthly_shortfall == Decimal("130000")

    assert scenario.after.monthly_available == Decimal("550000")
    assert scenario.after.monthly_shortfall == Decimal("630000")


def test_scenario_id_and_label_reflect_ratio() -> None:
    debts, income, household = _kimhaneul_inputs()
    scenario = income_drop(debts, income, household, ratio=Decimal("0.3"))
    assert scenario.scenario_id == "income_drop_30"
    assert "30%" in scenario.label


def test_scenario_does_not_mutate_original_debts_or_household() -> None:
    debts, income, household = _kimhaneul_inputs()
    income_drop(debts, income, household)
    assert income.monthly_net_income.value == Decimal("2500000")


def test_missing_income_stays_none_after_drop() -> None:
    debts, _, household = _kimhaneul_inputs()
    income = IncomeProfile()
    scenario = income_drop(debts, income, household)
    assert scenario.before.dti_ratio is None
    assert scenario.after.dti_ratio is None
