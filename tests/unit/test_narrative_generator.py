"""T14 — 설명 생성기 테스트: fallback 대체, 그라운딩 재시도, 예외 미노출."""

from __future__ import annotations

from decimal import Decimal

from dn.domain.enums import PathStatus, SectionKind
from dn.domain.models import CashflowResult, PathCandidate, PolicyRef
from dn.llm.client import StubClient
from dn.narrative.generator import build_allowed_set, generate


def _cashflow() -> CashflowResult:
    return CashflowResult(
        total_debt=Decimal("46000000"),
        monthly_total_payment=Decimal("1180000"),
        monthly_available=Decimal("1050000"),
        monthly_shortfall=Decimal("130000"),
        dti_ratio=Decimal("0.472"),
        max_overdue_days=42,
    )


def _paths() -> tuple[PathCandidate, ...]:
    from datetime import date

    return (
        PathCandidate(
            path_id="pre_debt_adjustment",
            name="사전채무조정",
            priority=2,
            agency="신용회복위원회",
            status=PathStatus.NEEDS_INFO,
            policy_ref=PolicyRef(
                card_id="pre_debt_adjustment",
                card_version="2026-08-13.1",
                title="사전채무조정",
                policy_base_date=date(2026, 8, 13),
                verified=False,
            ),
        ),
    )


def test_no_client_uses_template_fallback_directly() -> None:
    narrative = generate(_cashflow(), _paths(), client=None)
    cashflow_section = next(s for s in narrative.sections if s.section == SectionKind.CASHFLOW)
    assert cashflow_section.fallback_used is True
    assert cashflow_section.generated_by_llm is False
    assert "13만 원" in cashflow_section.text or "130,000" in cashflow_section.text


def test_grounded_llm_response_is_accepted() -> None:
    client = StubClient(response="매달 13만 원이 부족합니다.")
    narrative = generate(_cashflow(), _paths(), client=client)
    cashflow_section = next(s for s in narrative.sections if s.section == SectionKind.CASHFLOW)
    assert cashflow_section.generated_by_llm is True
    assert cashflow_section.fallback_used is False
    assert cashflow_section.grounded is True


def test_ungrounded_response_falls_back_to_template_after_retry() -> None:
    client = StubClient(response="매달 9,999만원이 부족하며 신청이 확정됩니다.")
    narrative = generate(_cashflow(), _paths(), client=client)
    cashflow_section = next(s for s in narrative.sections if s.section == SectionKind.CASHFLOW)
    assert cashflow_section.fallback_used is True
    assert cashflow_section.generated_by_llm is False


def test_retries_once_before_falling_back() -> None:
    calls = {"n": 0}

    def responder(system: str, user: str) -> str:
        calls["n"] += 1
        return "허용되지 않은 9,999만원이 등장합니다."

    client = StubClient(response=responder)
    generate(_cashflow(), _paths(), client=client)
    # 섹션마다 최초 시도 + 재시도 1회 = 2번. 현금흐름/경로 2개 섹션 = 4번.
    assert calls["n"] == 4


def test_llm_exception_does_not_propagate_to_caller() -> None:
    def raising_responder(system: str, user: str) -> str:
        raise RuntimeError("네트워크 오류 시뮬레이션")

    client = StubClient(response=raising_responder)
    narrative = generate(_cashflow(), _paths(), client=client)  # 예외 없이 완료되어야 한다
    cashflow_section = next(s for s in narrative.sections if s.section == SectionKind.CASHFLOW)
    assert cashflow_section.fallback_used is True


def test_build_allowed_set_includes_ordinals_one_to_ten() -> None:
    allowed = build_allowed_set(_cashflow(), (), ())
    for i in range(1, 11):
        assert Decimal(i) in allowed


def test_build_allowed_set_includes_policy_base_date_parts() -> None:
    allowed = build_allowed_set(_cashflow(), (), _paths())
    assert Decimal(2026) in allowed
    assert Decimal(8) in allowed
    assert Decimal(13) in allowed
