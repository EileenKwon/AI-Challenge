"""T13 — 트리아지 테스트. 7개 신호 각각 단독 발동, REFER 시에도 cashflow 반환."""

from __future__ import annotations

from decimal import Decimal

from dn.domain.enums import TriageDecision
from dn.domain.models import CashflowResult
from dn.rules.triage import evaluate


def _base_facts(**overrides):
    facts = {
        "max_overdue_days": 10,
        "monthly_available": Decimal("500000"),
        "court_proceeding_ongoing": False,
        "has_guarantee_debt": False,
        "has_tax_debt": False,
        "has_private_debt": False,
        "has_secured_debt": False,
        "legal_dispute": False,
        "seizure_ongoing": False,
    }
    facts.update(overrides)
    return facts


def _clean_quality(**overrides):
    quality = {"has_unresolved_conflicts": False, "low_confidence": False}
    quality.update(overrides)
    return quality


def test_no_signal_yields_proceed() -> None:
    result = evaluate(_base_facts(), _clean_quality())
    assert result.decision == TriageDecision.PROCEED
    assert result.signals == ()


# --- 7개 신호 단독 발동 ----------------------------------------------------------


def test_signal_severe_overdue() -> None:
    result = evaluate(_base_facts(max_overdue_days=90), _clean_quality())
    assert result.decision == TriageDecision.REFER
    assert "연체 90일 이상" in result.signals


def test_signal_no_repayment_capacity() -> None:
    result = evaluate(_base_facts(monthly_available=Decimal("0")), _clean_quality())
    assert result.decision == TriageDecision.REFER
    assert "상환여력 사실상 없음" in result.signals

    negative = evaluate(_base_facts(monthly_available=Decimal("-100000")), _clean_quality())
    assert "상환여력 사실상 없음" in negative.signals


def test_signal_court_proceeding() -> None:
    result = evaluate(_base_facts(court_proceeding_ongoing=True), _clean_quality())
    assert result.decision == TriageDecision.REFER
    assert "법원 절차 진행 중" in result.signals


def test_signal_guarantee_tax_or_private_debt() -> None:
    for key in ("has_guarantee_debt", "has_tax_debt", "has_private_debt"):
        result = evaluate(_base_facts(**{key: True}), _clean_quality())
        assert result.decision == TriageDecision.REFER
        assert "보증·조세·사인 간 채무" in result.signals


def test_signal_secured_debt_with_complex_property() -> None:
    result = evaluate(_base_facts(has_secured_debt=True, legal_dispute=True), _clean_quality())
    assert result.decision == TriageDecision.REFER
    assert "담보 채무와 복잡한 재산관계" in result.signals


def test_secured_debt_alone_without_legal_dispute_does_not_trigger() -> None:
    result = evaluate(_base_facts(has_secured_debt=True), _clean_quality())
    assert "담보 채무와 복잡한 재산관계" not in result.signals


def test_signal_seizure_ongoing() -> None:
    result = evaluate(_base_facts(seizure_ongoing=True), _clean_quality())
    assert result.decision == TriageDecision.REFER
    assert "강제집행·압류 진행 중" in result.signals


def test_signal_unresolved_conflict_or_low_confidence() -> None:
    result = evaluate(_base_facts(), _clean_quality(has_unresolved_conflicts=True))
    assert result.decision == TriageDecision.REFER
    assert "모순 미해소 또는 추출 신뢰도 저하" in result.signals

    result2 = evaluate(_base_facts(), _clean_quality(low_confidence=True))
    assert result2.decision == TriageDecision.REFER
    assert "모순 미해소 또는 추출 신뢰도 저하" in result2.signals


def test_multiple_signals_all_recorded() -> None:
    result = evaluate(_base_facts(max_overdue_days=90, seizure_ongoing=True), _clean_quality())
    assert len(result.signals) == 2


def test_referral_agency_set_on_refer() -> None:
    result = evaluate(_base_facts(max_overdue_days=90), _clean_quality())
    assert result.referral_agency is not None
    assert result.message != ""


# --- REFER 여도 cashflow 는 그대로 제공된다 -------------------------------------


def test_refer_decision_does_not_affect_already_computed_cashflow() -> None:
    cashflow = CashflowResult(
        total_debt=Decimal("46000000"),
        monthly_total_payment=Decimal("1180000"),
        monthly_available=Decimal("0"),  # 상환여력 없음 → REFER 신호
        monthly_shortfall=Decimal("1180000"),
        max_overdue_days=95,
    )
    facts = _base_facts(
        max_overdue_days=cashflow.max_overdue_days,
        monthly_available=cashflow.monthly_available,
    )
    result = evaluate(facts, _clean_quality())

    assert result.decision == TriageDecision.REFER
    # cashflow 는 트리아지 호출과 무관하게 그대로 확정 숫자를 유지한다.
    assert cashflow.total_debt == Decimal("46000000")
    assert cashflow.monthly_shortfall == Decimal("1180000")
