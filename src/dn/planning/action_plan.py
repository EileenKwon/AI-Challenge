"""7일 행동계획 생성 — 사용자 상황에 따라 우선순위가 조정된다.

액션 항목 자체는 `config/action_templates.yaml` 에서만 나온다. LLM 은 문구
다듬기에만 관여하며 새 액션을 만들 수 없다. LLM 없이도 완전한 계획이
나와야 한다(T16 세부 규칙).
"""

from __future__ import annotations

from typing import Any

import yaml

from dn.domain.enums import ActionTiming
from dn.domain.models import ActionItem, ActionPlan
from dn.settings import Settings, get_settings

_OVERDUE_IMMINENT_RANGES = ((25, 30), (85, 89))
_TOP_BOOST = -100
_UPPER_BOOST = -50


def _load_templates(settings: Settings) -> dict[str, Any]:
    path = settings.resolve("config/action_templates.yaml")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _is_overdue_imminent(max_overdue_days: int | None) -> bool:
    if max_overdue_days is None:
        return False
    return any(lo <= max_overdue_days <= hi for lo, hi in _OVERDUE_IMMINENT_RANGES)


def build_plan(
    *,
    max_overdue_days: int | None,
    income_proof_available: bool | None,
    debts_incomplete: bool,
    income_drop_signal: bool,
    settings: Settings | None = None,
) -> ActionPlan:
    """규칙 기반으로 우선순위를 조정한 7일 행동계획을 만든다.

    조정 규칙: 연체 임박(25~30일 또는 85~89일) → 상담 예약 최상단 /
    소득증빙 미확인 → 서류 확인 상단 / 채무 목록 불완전 → 목록 확인 상단 /
    실직·폐업(소득 급감 신호) → 복합지원 상담 추가.
    """
    settings = settings or get_settings()
    raw = _load_templates(settings)
    items_raw = list(raw.get("items", []))

    boosts: dict[str, int] = {}
    if _is_overdue_imminent(max_overdue_days):
        boosts["book_consultation"] = _TOP_BOOST
    if income_proof_available is None:
        boosts["prepare_documents"] = _UPPER_BOOST
    if debts_incomplete:
        boosts["check_debt_list"] = _UPPER_BOOST

    ordered = sorted(items_raw, key=lambda item: (boosts.get(item["id"], 0), item["order"]))

    action_items = [
        ActionItem(timing=ActionTiming(item["timing"]), order=i + 1, text=item["text"])
        for i, item in enumerate(ordered)
    ]

    complex_support_areas: tuple[str, ...] = ()
    if income_drop_signal:
        for cond in raw.get("conditional_items", []):
            if cond.get("trigger") != "income_drop_signal":
                continue
            action_items.append(
                ActionItem(
                    timing=ActionTiming(cond["timing"]),
                    order=len(action_items) + 1,
                    text=cond["text"],
                    related_agency=cond.get("related_agency"),
                )
            )
            complex_support_areas = (cond.get("related_agency", ""),)

    return ActionPlan(items=tuple(action_items), complex_support_areas=complex_support_areas)
