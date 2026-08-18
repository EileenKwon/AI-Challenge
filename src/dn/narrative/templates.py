"""LLM 실패 시 결정론적 fallback 문장.

값을 그대로 보간하므로 정의상 항상 그라운딩된다. 확정 표현은 현금흐름
섹션에서만 쓴다(제도 섹션은 허용되지 않는다, T15).
"""

from __future__ import annotations

from dn.cashflow.formatting import format_ratio, format_won
from dn.domain.enums import SectionKind
from dn.domain.models import CashflowResult, NarrativeSection, PathCandidate


def cashflow_fallback(cashflow: CashflowResult) -> NarrativeSection:
    """현금흐름 섹션 템플릿 문장."""
    shortfall = cashflow.monthly_shortfall
    if shortfall > 0:
        headline = f"매달 {format_won(shortfall)}이 부족합니다."
    elif shortfall < 0:
        headline = f"매달 {format_won(abs(shortfall))}의 여유 자금이 있습니다."
    else:
        headline = "월 가용재원과 예정 상환액이 정확히 일치합니다."

    detail = (
        f"월 실수령소득에서 필수 지출을 제외하면 {format_won(cashflow.monthly_available)}이 남고, "
        f"현재 매달 갚아야 할 금액은 {format_won(cashflow.monthly_total_payment)}입니다."
    )
    parts = [headline, detail]
    if cashflow.dti_ratio is not None:
        parts.append(f"소득의 {format_ratio(cashflow.dti_ratio)}가 상환에 들어가고 있습니다.")

    return NarrativeSection(
        section=SectionKind.CASHFLOW,
        text=" ".join(parts),
        generated_by_llm=False,
        grounded=True,
        fallback_used=True,
    )


def path_fallback(paths: tuple[PathCandidate, ...]) -> NarrativeSection:
    """제도 경로 섹션 템플릿 문장. 확정 표현을 쓰지 않는다."""
    if not paths:
        text = "현재 정보로는 검토 가능한 경로를 찾지 못했습니다. 전문상담을 통해 확인해 주세요."
    else:
        names = ", ".join(p.name for p in paths)
        text = (
            f"검토 가능한 경로 후보는 {names}입니다. "
            "신청 가능 여부는 확정되지 않았으며 공식 상담을 통해 확인해야 합니다."
        )

    return NarrativeSection(
        section=SectionKind.PATH,
        text=text,
        generated_by_llm=False,
        grounded=True,
        fallback_used=True,
    )
