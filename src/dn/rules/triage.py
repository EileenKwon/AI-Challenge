"""트리아지 — 자동 분석 대신 전문상담 우선 연결이 필요한 경우를 판별한다 (기획서 3.2).

REFER 판정이어도 현금흐름 결과는 그대로 제공한다. 생략되는 것은 규칙 엔진뿐이다
(오케스트레이터가 이 순서를 지킨다, T18).
"""

from __future__ import annotations

from typing import Any

from dn.domain.enums import TriageDecision
from dn.domain.models import TriageResult

_SEVERE_OVERDUE_DAYS = 90
_REFERRAL_AGENCY = "신용회복위원회 공식 상담 창구"
_REFER_MESSAGE = (
    "자동 분석 대신 전문상담을 우선 연결합니다. 현금흐름 확정 숫자는 그대로 제공됩니다."
)


def evaluate(facts: dict[str, Any], extraction_quality: dict[str, Any]) -> TriageResult:
    """7개 신호 중 하나라도 해당하면 `REFER`, 아니면 `PROCEED`."""
    signals: list[str] = []

    if (facts.get("max_overdue_days") or 0) >= _SEVERE_OVERDUE_DAYS:
        signals.append("연체 90일 이상")

    monthly_available = facts.get("monthly_available")
    if monthly_available is not None and monthly_available <= 0:
        signals.append("상환여력 사실상 없음")

    if facts.get("court_proceeding_ongoing") is True:
        signals.append("법원 절차 진행 중")

    if (
        facts.get("has_guarantee_debt") is True
        or facts.get("has_tax_debt") is True
        or facts.get("has_private_debt") is True
    ):
        signals.append("보증·조세·사인 간 채무")

    if facts.get("has_secured_debt") is True and facts.get("legal_dispute") is True:
        signals.append("담보 채무와 복잡한 재산관계")

    if facts.get("seizure_ongoing") is True:
        signals.append("강제집행·압류 진행 중")

    if extraction_quality.get("has_unresolved_conflicts") or extraction_quality.get(
        "low_confidence"
    ):
        signals.append("모순 미해소 또는 추출 신뢰도 저하")

    if signals:
        return TriageResult(
            decision=TriageDecision.REFER,
            signals=tuple(signals),
            referral_agency=_REFERRAL_AGENCY,
            message=_REFER_MESSAGE,
        )

    return TriageResult(decision=TriageDecision.PROCEED, signals=(), message="")
