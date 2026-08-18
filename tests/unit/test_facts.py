"""T12 — facts 조립 테스트."""

from __future__ import annotations

from decimal import Decimal

from dn.domain.enums import FieldSource
from dn.domain.models import CashflowResult, Debt, IncomeProfile, SituationFlags
from dn.domain.provenance import Tracked
from dn.rules.facts import build_facts


def _known(value):
    return Tracked(value=value, source=FieldSource.DOCUMENT)


def test_build_facts_maps_cashflow_fields() -> None:
    cashflow = CashflowResult(
        total_debt=Decimal("1000000"),
        monthly_total_payment=Decimal("100000"),
        monthly_available=Decimal("50000"),
        monthly_shortfall=Decimal("50000"),
        max_overdue_days=42,
    )
    facts = build_facts((), IncomeProfile(), cashflow, SituationFlags())
    assert facts["max_overdue_days"] == 42
    assert facts["total_debt"] == Decimal("1000000")


def test_build_facts_maps_income_drop_signal_from_flags() -> None:
    cashflow = CashflowResult(
        total_debt=Decimal("0"),
        monthly_total_payment=Decimal("0"),
        monthly_available=Decimal("0"),
        monthly_shortfall=Decimal("0"),
    )
    flags = SituationFlags(recent_job_loss=_known(True))
    facts = build_facts((), IncomeProfile(), cashflow, flags)
    assert facts["income_drop_signal"] is True


def test_build_facts_maps_secured_debt_from_debts() -> None:
    cashflow = CashflowResult(
        total_debt=Decimal("0"),
        monthly_total_payment=Decimal("0"),
        monthly_available=Decimal("0"),
        monthly_shortfall=Decimal("0"),
    )
    debts = (Debt(debt_id="d0", is_secured=_known(True)),)
    facts = build_facts(debts, IncomeProfile(), cashflow, SituationFlags())
    assert facts["has_secured_debt"] is True


def test_build_facts_unknown_income_proof_stays_none() -> None:
    cashflow = CashflowResult(
        total_debt=Decimal("0"),
        monthly_total_payment=Decimal("0"),
        monthly_available=Decimal("0"),
        monthly_shortfall=Decimal("0"),
    )
    facts = build_facts((), IncomeProfile(), cashflow, SituationFlags())
    assert facts["income_proof_available"] is None
