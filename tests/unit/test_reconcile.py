"""T07 — 누락·모순 탐지 테스트.

7개 규칙(GAP_RATE, GAP_PAYMENT, GAP_EXECUTED_AT, GAP_INCOME_PROOF,
CONF_BALANCE_SUM, CONF_OVERDUE, IMPL_LIVING_COST) 각각의 양성·음성 케이스와,
기획서 15장 김하늘 사례(추출 직후 상태)를 검증한다.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from dn.domain.enums import FieldSource, ProductType
from dn.domain.models import Debt, ExtractionResult, HouseholdProfile, IncomeProfile
from dn.domain.provenance import Tracked
from dn.reconcile.conflict_detector import detect_conflicts
from dn.reconcile.gap_detector import detect_gaps
from dn.settings import get_settings


def _known(value):
    return Tracked(value=value, source=FieldSource.DOCUMENT)


def _unknown():
    return Tracked()


def _debt(
    *,
    debt_id: str = "d0",
    creditor: str | None = "A금융",
    balance: Decimal | None = Decimal("1000000"),
    overdue_days: int | None = 0,
    executed_at: date | None = date(2023, 1, 1),
    interest_rate: Decimal | None = None,
    monthly_payment: Decimal | None = None,
) -> Debt:
    return Debt(
        debt_id=debt_id,
        creditor=_known(creditor) if creditor is not None else _unknown(),
        product_type=_known(ProductType.CREDIT_LOAN),
        balance=_known(balance) if balance is not None else _unknown(),
        overdue_days=_known(overdue_days) if overdue_days is not None else _unknown(),
        executed_at=_known(executed_at) if executed_at is not None else _unknown(),
        is_secured=_known(False),
        interest_rate=_known(interest_rate) if interest_rate is not None else _unknown(),
        monthly_payment=_known(monthly_payment) if monthly_payment is not None else _unknown(),
    )


def _income(*, income_proof_available: bool | None = True) -> IncomeProfile:
    return IncomeProfile(
        income_proof_available=(
            _known(income_proof_available) if income_proof_available is not None else _unknown()
        )
    )


# --- GAP_RATE ---------------------------------------------------------------


def test_gap_rate_fires_when_interest_rate_missing() -> None:
    report = detect_gaps((_debt(interest_rate=None),), _income())
    assert any(g.rule_id == "GAP_RATE" for g in report.gaps)


def test_gap_rate_absent_when_interest_rate_known() -> None:
    report = detect_gaps((_debt(interest_rate=Decimal("0.15")),), _income())
    assert not any(g.rule_id == "GAP_RATE" for g in report.gaps)


# --- GAP_PAYMENT --------------------------------------------------------------


def test_gap_payment_fires_when_monthly_payment_missing() -> None:
    report = detect_gaps((_debt(monthly_payment=None),), _income())
    assert any(g.rule_id == "GAP_PAYMENT" for g in report.gaps)


def test_gap_payment_absent_when_monthly_payment_known() -> None:
    report = detect_gaps((_debt(monthly_payment=Decimal("100000")),), _income())
    assert not any(g.rule_id == "GAP_PAYMENT" for g in report.gaps)


# --- GAP_EXECUTED_AT -----------------------------------------------------------


def test_gap_executed_at_fires_when_missing() -> None:
    report = detect_gaps((_debt(executed_at=None),), _income())
    assert any(g.rule_id == "GAP_EXECUTED_AT" for g in report.gaps)


def test_gap_executed_at_absent_when_known() -> None:
    report = detect_gaps((_debt(executed_at=date(2022, 3, 1)),), _income())
    assert not any(g.rule_id == "GAP_EXECUTED_AT" for g in report.gaps)


# --- GAP_INCOME_PROOF ----------------------------------------------------------


def test_gap_income_proof_fires_when_unknown() -> None:
    report = detect_gaps((_debt(),), _income(income_proof_available=None))
    assert any(g.rule_id == "GAP_INCOME_PROOF" for g in report.gaps)


def test_gap_income_proof_absent_when_known() -> None:
    report = detect_gaps((_debt(),), _income(income_proof_available=False))
    assert not any(g.rule_id == "GAP_INCOME_PROOF" for g in report.gaps)


# --- CONF_BALANCE_SUM ----------------------------------------------------------


def test_conf_balance_sum_fires_on_mismatch() -> None:
    debts = (
        _debt(debt_id="d0", balance=Decimal("10000000")),
        _debt(debt_id="d1", balance=Decimal("5000000")),
    )
    extraction = ExtractionResult(debts=debts, doc_total_balance=_known(Decimal("99000000")))
    report = detect_conflicts(extraction, HouseholdProfile())
    assert any(c.rule_id == "CONF_BALANCE_SUM" for c in report.conflicts)


def test_conf_balance_sum_absent_when_consistent() -> None:
    debts = (
        _debt(debt_id="d0", balance=Decimal("10000000")),
        _debt(debt_id="d1", balance=Decimal("5000000")),
    )
    extraction = ExtractionResult(debts=debts, doc_total_balance=_known(Decimal("15000000")))
    report = detect_conflicts(extraction, HouseholdProfile())
    assert not any(c.rule_id == "CONF_BALANCE_SUM" for c in report.conflicts)


# --- CONF_OVERDUE --------------------------------------------------------------


def test_conf_overdue_fires_and_adopts_max_value() -> None:
    debts = (
        _debt(debt_id="d0", creditor="A금융", overdue_days=10),
        _debt(debt_id="d1", creditor="A금융", overdue_days=42),
    )
    extraction = ExtractionResult(debts=debts)
    report = detect_conflicts(extraction, HouseholdProfile())
    matches = [c for c in report.conflicts if c.rule_id == "CONF_OVERDUE"]
    assert len(matches) == 1
    assert matches[0].resolved is True
    assert "42" in matches[0].resolution


def test_conf_overdue_absent_when_consistent() -> None:
    debts = (
        _debt(debt_id="d0", creditor="A금융", overdue_days=10),
        _debt(debt_id="d1", creditor="B카드", overdue_days=42),
    )
    extraction = ExtractionResult(debts=debts)
    report = detect_conflicts(extraction, HouseholdProfile())
    assert not any(c.rule_id == "CONF_OVERDUE" for c in report.conflicts)


# --- IMPL_LIVING_COST ----------------------------------------------------------


def test_impl_living_cost_disabled_by_default_never_fires() -> None:
    settings = get_settings()
    assert settings.config.reconcile.living_cost_check_enabled is False
    household = HouseholdProfile(essential_living_cost=_known(Decimal("1")), dependents=_known(0))
    extraction = ExtractionResult(debts=())
    report = detect_conflicts(extraction, household, settings=settings)
    assert not any(c.rule_id == "IMPL_LIVING_COST" for c in report.conflicts)


def test_impl_living_cost_fires_when_enabled_and_below_floor() -> None:
    base = get_settings()
    enabled_reconcile = base.config.reconcile.model_copy(
        update={"living_cost_check_enabled": True, "living_cost_floor_per_person": 1_000_000}
    )
    enabled_config = base.config.model_copy(update={"reconcile": enabled_reconcile})
    enabled_settings = base.model_copy(update={"config": enabled_config})

    household = HouseholdProfile(
        essential_living_cost=_known(Decimal("500000")), dependents=_known(0)
    )
    extraction = ExtractionResult(debts=())
    report = detect_conflicts(extraction, household, settings=enabled_settings)
    assert any(c.rule_id == "IMPL_LIVING_COST" for c in report.conflicts)


# --- 기획서 15장 김하늘 사례 (추출 직후, 보완 입력 이전 상태) ---------------------


def test_kimhaneul_case_detects_rate_payment_and_income_proof_gaps() -> None:
    debts = (
        _debt(
            debt_id="d0",
            creditor="A금융",
            balance=Decimal("25000000"),
            overdue_days=42,
            executed_at=date(2023, 5, 1),
        ),
        _debt(
            debt_id="d1",
            creditor="B카드",
            balance=Decimal("14000000"),
            overdue_days=0,
            executed_at=date(2022, 1, 10),
        ),
        _debt(
            debt_id="d2",
            creditor="C캐피탈",
            balance=Decimal("7000000"),
            overdue_days=0,
            executed_at=date(2021, 6, 20),
        ),
    )
    income = _income(income_proof_available=None)

    report = detect_gaps(debts, income)
    rule_ids = {g.rule_id for g in report.gaps}

    assert rule_ids == {"GAP_RATE", "GAP_PAYMENT", "GAP_INCOME_PROOF"}
