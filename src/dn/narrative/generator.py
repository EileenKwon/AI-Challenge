"""설명 생성기 — LLM 이 확정 값을 문장으로 옮기되, 그라운딩 검증을 통과한 것만 채택한다.

허용 집합 구성: `CashflowResult` 의 전 금액·비율 / 각 `Debt` 의 잔액·금리·
연체일수 / 정책 카드에 명시된 숫자(조건 근거값·우선순위) / 정책 기준일 /
서수 1~10.

그라운딩 실패 시 재생성 1회 → 재차 실패 시 템플릿 fallback 으로 대체되고,
LLM 호출 실패를 포함한 예외는 사용자에게 노출되지 않는다.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from typing import Any

from dn.cashflow.formatting import format_ratio, format_won
from dn.domain.enums import SectionKind
from dn.domain.models import CashflowResult, Debt, Narrative, NarrativeSection, PathCandidate
from dn.llm.client import LLMClient
from dn.narrative import templates
from dn.narrative.grounding import GroundingSet, validate_grounding
from dn.narrative.prompts import NARRATIVE_SYSTEM_PROMPT, build_cashflow_prompt, build_path_prompt

_ORDINALS: frozenset[Decimal] = frozenset(Decimal(i) for i in range(1, 11))
_CASHFLOW_MONEY_FIELDS = (
    "total_debt",
    "monthly_total_payment",
    "monthly_available",
    "monthly_shortfall",
)
_CASHFLOW_RATIO_FIELDS = (
    "dti_ratio",
    "secured_ratio",
    "weighted_avg_rate",
    "max_rate",
    "recent_debt_ratio",
    "completeness",
)


def build_allowed_set(
    cashflow: CashflowResult, debts: tuple[Debt, ...], paths: tuple[PathCandidate, ...]
) -> GroundingSet:
    """CashflowResult/Debt/정책 카드/정책 기준일/서수 1~10 을 모아 허용 집합을 만든다."""
    values: set[Decimal] = set(_ORDINALS)

    for field_name in (*_CASHFLOW_MONEY_FIELDS, *_CASHFLOW_RATIO_FIELDS):
        value = getattr(cashflow, field_name, None)
        if value is not None:
            values.add(abs(Decimal(value)))
            values.add(Decimal(value))
    if cashflow.max_overdue_days is not None:
        values.add(Decimal(cashflow.max_overdue_days))

    for debt in debts:
        if debt.balance.value is not None:
            values.add(Decimal(debt.balance.value))
        if debt.interest_rate.value is not None:
            values.add(Decimal(debt.interest_rate.value))
        if debt.overdue_days.value is not None:
            values.add(Decimal(debt.overdue_days.value))

    for path in paths:
        values.add(Decimal(path.priority))
        for condition in (*path.met, *path.unknown, *path.not_met):
            if condition.evidence is None:
                continue
            try:
                values.add(Decimal(condition.evidence))
            except InvalidOperation:
                continue
        if path.policy_ref is not None:
            d = path.policy_ref.policy_base_date
            values.update({Decimal(d.year), Decimal(d.month), Decimal(d.day)})

    return frozenset(values)


def _cashflow_summary(cashflow: CashflowResult) -> dict[str, Any]:
    shortfall_label = "월 부족액" if cashflow.monthly_shortfall >= 0 else "월 여유자금"
    return {
        "월 가용재원": format_won(cashflow.monthly_available),
        "월 총 예정 상환액": format_won(cashflow.monthly_total_payment),
        shortfall_label: format_won(abs(cashflow.monthly_shortfall)),
        "부담률": format_ratio(cashflow.dti_ratio),
    }


def _path_summaries(paths: tuple[PathCandidate, ...]) -> list[dict[str, Any]]:
    return [{"이름": p.name, "담당기관": p.agency, "상태": p.status.value} for p in paths]


def _generate_section(
    *,
    section: SectionKind,
    build_prompt: Callable[[], str],
    allowed: GroundingSet,
    client: LLMClient | None,
    fallback: Callable[[], NarrativeSection],
) -> NarrativeSection:
    if client is not None:
        for _ in range(2):  # 최초 시도 + 그라운딩 실패 시 재생성 1회
            try:
                text = client.complete(system=NARRATIVE_SYSTEM_PROMPT, user=build_prompt())
            except Exception:
                break
            if validate_grounding(text, allowed).grounded:
                return NarrativeSection(
                    section=section,
                    text=text,
                    generated_by_llm=True,
                    grounded=True,
                    fallback_used=False,
                )
    return fallback()


def generate(
    cashflow: CashflowResult,
    paths: tuple[PathCandidate, ...],
    debts: tuple[Debt, ...] = (),
    *,
    client: LLMClient | None = None,
) -> Narrative:
    """현금흐름과 제도 경로를 문장으로 옮긴다."""
    allowed = build_allowed_set(cashflow, debts, paths)

    cashflow_section = _generate_section(
        section=SectionKind.CASHFLOW,
        build_prompt=lambda: build_cashflow_prompt(_cashflow_summary(cashflow)),
        allowed=allowed,
        client=client,
        fallback=lambda: templates.cashflow_fallback(cashflow),
    )
    path_section = _generate_section(
        section=SectionKind.PATH,
        build_prompt=lambda: build_path_prompt(_path_summaries(paths)),
        allowed=allowed,
        client=client,
        fallback=lambda: templates.path_fallback(paths),
    )

    return Narrative(sections=(cashflow_section, path_section))
