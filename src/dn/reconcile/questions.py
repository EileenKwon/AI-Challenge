"""3단계 누락정보 확인 질문 — 고정 5문항 + 조건부 3문항.

문구·발동 트리거 이름은 `config/questions.yaml` 에 있다. 코드에는 트리거 평가
로직만 둔다. 조건부 질문 발동 조건은 담보채무 존재 / 연체 존재 / 소득 급감 신호다.
"""

from __future__ import annotations

from typing import Any

import yaml

from dn.domain.models import Debt, Question, SituationFlags
from dn.settings import Settings, get_settings


def _question_from_raw(raw: dict[str, Any]) -> Question:
    return Question(
        qid=raw["qid"],
        text=raw["text"],
        kind=raw["kind"],
        required=raw.get("required", True),
        conditional_on=raw.get("conditional_on"),
        skippable=raw.get("skippable", False),
        skip_impact=raw.get("skip_impact"),
    )


def _load_questions_yaml(settings: Settings) -> dict[str, Any]:
    return yaml.safe_load(settings.questions_path.read_text(encoding="utf-8")) or {}


def load_fixed_questions(*, settings: Settings | None = None) -> tuple[Question, ...]:
    settings = settings or get_settings()
    raw = _load_questions_yaml(settings)
    return tuple(_question_from_raw(q) for q in raw.get("fixed", []))


def load_conditional_questions(*, settings: Settings | None = None) -> tuple[Question, ...]:
    settings = settings or get_settings()
    raw = _load_questions_yaml(settings)
    return tuple(_question_from_raw(q) for q in raw.get("conditional", []))


def has_secured_debt(debts: tuple[Debt, ...]) -> bool:
    return any(d.is_secured.value is True for d in debts)


def has_overdue(debts: tuple[Debt, ...]) -> bool:
    return any((d.overdue_days.value or 0) > 0 for d in debts)


def has_income_drop_signal(flags: SituationFlags) -> bool:
    return bool(flags.recent_job_loss.value) or bool(flags.business_closed.value)


def select_active_questions(
    *,
    secured_debt_present: bool,
    overdue_present: bool,
    income_drop_present: bool,
    settings: Settings | None = None,
) -> tuple[Question, ...]:
    """고정 5문항 전체와, 발동 조건을 만족한 조건부 문항만 이어붙여 반환한다."""
    settings = settings or get_settings()
    fixed = load_fixed_questions(settings=settings)
    conditional = load_conditional_questions(settings=settings)

    triggers = {
        "has_secured_debt": secured_debt_present,
        "has_overdue": overdue_present,
        "income_drop_signal": income_drop_present,
    }
    active_conditional = tuple(q for q in conditional if triggers.get(q.conditional_on, False))
    return fixed + active_conditional
