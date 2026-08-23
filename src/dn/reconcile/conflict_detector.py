"""서로 어긋나는 정보 탐지. LLM 미사용.

`CONF_OVERDUE` 충돌 시 보수적으로 연체일수 최댓값을 채택하고, 채택 사실을
`Conflict.resolution` 에 남겨 화면에 표시한다.

`IMPL_LIVING_COST` 임계치는 근거가 확인되기 전까지
`config.yaml: reconcile.living_cost_check_enabled` 로 비활성화되어 있다
(근거 없는 숫자를 코드에 박지 않는다, AGENTS.md 절대 규칙 9).
"""

from __future__ import annotations

from decimal import Decimal

from dn.domain.models import Conflict, ConflictReport, Debt, ExtractionResult, HouseholdProfile
from dn.settings import Settings, get_settings

_BALANCE_SUM_TOLERANCE = Decimal("1")


def _detect_balance_sum_conflict(extraction: ExtractionResult) -> Conflict | None:
    doc_total = extraction.doc_total_balance.value
    if doc_total is None:
        return None
    known_balances = [d.balance.value for d in extraction.debts if d.balance.value is not None]
    if not known_balances:
        return None
    computed_sum = sum(known_balances, Decimal("0"))
    if abs(computed_sum - doc_total) <= _BALANCE_SUM_TOLERANCE:
        return None
    return Conflict(
        rule_id="CONF_BALANCE_SUM",
        label="채무 잔액 합계 불일치",
        values=(f"개별 채무 합계 {computed_sum}", f"문서상 총액 {doc_total}"),
        resolution=None,
        resolved=False,
    )


def _detect_overdue_conflict(debts: tuple[Debt, ...]) -> Conflict | None:
    by_creditor: dict[str, list[int]] = {}
    for debt in debts:
        creditor = debt.creditor.value
        overdue = debt.overdue_days.value
        if creditor is None or overdue is None:
            continue
        by_creditor.setdefault(creditor.strip(), []).append(overdue)

    for creditor, values in by_creditor.items():
        distinct = sorted(set(values))
        if len(distinct) <= 1:
            continue
        chosen = max(distinct)
        return Conflict(
            rule_id="CONF_OVERDUE",
            label=f"{creditor} 연체일수 불일치",
            values=tuple(str(v) for v in distinct),
            resolution=f"보수적으로 최댓값 {chosen}일 채택",
            resolved=True,
        )
    return None


def _detect_implied_living_cost_conflict(
    household: HouseholdProfile, *, settings: Settings
) -> Conflict | None:
    cfg = settings.config.reconcile
    if not cfg.living_cost_check_enabled:
        return None
    cost = household.essential_living_cost.value
    if cost is None:
        return None
    household_size = (household.dependents.value or 0) + 1
    floor_won = cfg.living_cost_floor(household_size)
    if floor_won is None or floor_won <= 0:
        return None
    floor = Decimal(floor_won)
    if cost >= floor:
        return None
    return Conflict(
        rule_id="IMPL_LIVING_COST",
        label="필수생활비가 가구원 수 대비 낮게 입력됨",
        values=(f"입력값 {cost}", f"기준 하한 {floor}"),
        resolution=None,
        resolved=False,
    )


def detect_conflicts(
    extraction: ExtractionResult,
    household: HouseholdProfile,
    *,
    settings: Settings | None = None,
) -> ConflictReport:
    """추출 결과와 가구 정보에서 상충되는 정보를 찾는다."""
    settings = settings or get_settings()

    conflicts: list[Conflict] = []
    balance_conflict = _detect_balance_sum_conflict(extraction)
    if balance_conflict is not None:
        conflicts.append(balance_conflict)
    overdue_conflict = _detect_overdue_conflict(extraction.debts)
    if overdue_conflict is not None:
        conflicts.append(overdue_conflict)
    living_cost_conflict = _detect_implied_living_cost_conflict(household, settings=settings)
    if living_cost_conflict is not None:
        conflicts.append(living_cost_conflict)

    return ConflictReport(conflicts=tuple(conflicts))
