"""규칙 엔진 — 정책 카드로 회복경로 후보를 선별한다. 판정이 아니라 후보 선별이다.

경로 상태 판정 순서 (반드시 이 순서):
  제외조건 중 하나라도 MET          → EXCLUDED
  required 조건 중 하나라도 NOT_MET → EXCLUDED
  required 조건 중 하나라도 UNKNOWN → NEEDS_INFO
  전부 MET                          → CANDIDATE

정렬: (status 순위, card.priority, unknown 개수 오름차순) → 상위 3개 반환.
EXCLUDED 는 목록에서 빼되 사유를 `excluded_paths` 에 보관한다.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from dn.domain.enums import ConditionState, PathStatus
from dn.domain.models import ConditionResult, PathCandidate, PolicyRef, RuleEngineResult
from dn.rules.condition_eval import evaluate as evaluate_condition
from dn.rules.policy_card import PolicyCard, PolicyCondition

_MAX_PATHS = 3
_STATUS_RANK = {PathStatus.CANDIDATE: 0, PathStatus.NEEDS_INFO: 1}


def _evaluate_card(
    card: PolicyCard, facts: dict[str, Any]
) -> tuple[PathStatus, list[ConditionResult], list[ConditionResult], list[ConditionResult]]:
    """카드 1개를 평가해 (status, met, unknown, not_met) 을 반환한다."""
    exclusion_results = [PolicyCondition.model_validate(exc) for exc in card.exclusions]
    exclusion_states = [evaluate_condition(c, facts) for c in exclusion_results]
    if any(r.state == ConditionState.MET for r in exclusion_states):
        return PathStatus.EXCLUDED, [], [], []

    results = [evaluate_condition(c, facts) for c in card.conditions]
    met = [r for r in results if r.state == ConditionState.MET]
    unknown = [r for r in results if r.state == ConditionState.UNKNOWN]
    not_met = [r for r in results if r.state == ConditionState.NOT_MET]

    if any(r.state == ConditionState.NOT_MET and r.required for r in results):
        return PathStatus.EXCLUDED, met, unknown, not_met
    if any(r.state == ConditionState.UNKNOWN and r.required for r in results):
        return PathStatus.NEEDS_INFO, met, unknown, not_met
    return PathStatus.CANDIDATE, met, unknown, not_met


def _to_path_candidate(
    card: PolicyCard,
    status: PathStatus,
    met: list[ConditionResult],
    unknown: list[ConditionResult],
    not_met: list[ConditionResult],
) -> PathCandidate:
    policy_ref = PolicyRef(
        card_id=card.id,
        card_version=card.version,
        title=card.name,
        url=card.source.get("url"),
        policy_base_date=date.fromisoformat(card.policy_base_date),
        verified=card.verified,
    )
    return PathCandidate(
        path_id=card.id,
        name=card.name,
        priority=card.priority,
        agency=card.agency,
        status=status,
        met=tuple(met),
        unknown=tuple(unknown),
        not_met=tuple(not_met),
        swing_factors=tuple(card.swing_factors),
        policy_ref=policy_ref,
        consult_questions=tuple(card.consult_questions),
        why_final_check=card.why_final_check,
        excluded_reason=(
            "제외 조건 충족 또는 필수 조건 미충족" if status == PathStatus.EXCLUDED else None
        ),
    )


def evaluate(
    facts: dict[str, Any],
    cards: list[PolicyCard],
    *,
    dev_mode: bool = False,
    rule_version: str = "",
    policy_base_date: date | None = None,
    has_unresolved_conflicts: bool = False,
) -> RuleEngineResult:
    """카드 목록을 사실로 평가해 상위 3개 후보 경로를 담은 `RuleEngineResult` 를 만든다."""
    candidates: list[PathCandidate] = []
    excluded: list[PathCandidate] = []

    for card in cards:
        status, met, unknown, not_met = _evaluate_card(card, facts)
        path = _to_path_candidate(card, status, met, unknown, not_met)
        (excluded if status == PathStatus.EXCLUDED else candidates).append(path)

    candidates.sort(key=lambda p: (_STATUS_RANK[p.status], p.priority, len(p.unknown)))
    top = candidates[:_MAX_PATHS]

    undetermined_reasons: list[str] = []
    if facts.get("max_overdue_days") is None:
        undetermined_reasons.append("핵심 입력 미확인: 최대 연체일수")
    if facts.get("total_debt") is None:
        undetermined_reasons.append("핵심 입력 미확인: 총채무액")
    if has_unresolved_conflicts:
        undetermined_reasons.append("미해소된 상충 정보가 있습니다")
    if not cards:
        undetermined_reasons.append("사용 가능한 정책 카드가 없습니다")

    return RuleEngineResult(
        paths=tuple(top),
        excluded_paths=tuple(excluded),
        undetermined=bool(undetermined_reasons),
        undetermined_reasons=tuple(undetermined_reasons),
        rule_version=rule_version,
        policy_base_date=policy_base_date,
        dev_mode=dev_mode,
    )
