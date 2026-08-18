"""3-state 조건 평가기 — "모른다"(UNKNOWN)를 1급 상태로 유지한다.

`eval()`/`exec()` 를 쓰지 않는다. 선언형 연산자만 지원하며, 정의되지 않은
연산자를 만나면 조용히 `False` 로 처리하지 않고 예외를 던진다.
"""

from __future__ import annotations

from typing import Any

from dn.domain.enums import ConditionState
from dn.domain.models import ConditionResult
from dn.rules.policy_card import PolicyCondition

_SUPPORTED_OPS = frozenset(
    {"between", "lte", "gte", "lt", "gt", "eq", "in", "is_true", "is_false", "exists"}
)


class UnknownOperatorError(ValueError):
    """정의되지 않은 연산자."""


def _apply_op(op: str, field_value: Any, condition_value: Any) -> bool:
    if op == "between":
        low, high = condition_value
        return low <= field_value <= high
    if op == "lte":
        return field_value <= condition_value
    if op == "gte":
        return field_value >= condition_value
    if op == "lt":
        return field_value < condition_value
    if op == "gt":
        return field_value > condition_value
    if op == "eq":
        return field_value == condition_value
    if op == "in":
        return field_value in condition_value
    if op == "is_true":
        return field_value is True
    if op == "is_false":
        return field_value is False
    if op == "exists":
        return field_value is not None
    raise UnknownOperatorError(f"정의되지 않은 연산자입니다: {op!r}")


def evaluate(condition: PolicyCondition, facts: dict[str, Any]) -> ConditionResult:
    """`condition` 을 `facts` 로 평가해 3-state `ConditionResult` 를 만든다.

    필드가 `facts` 에 없거나 값이 `None` 이면 연산자와 무관하게 `UNKNOWN` 이다.
    `is_false` 처럼 `None` 이 그럴듯한 "아니오"로 보일 수 있는 연산자도 예외가
    아니다 — `None` 을 `NOT_MET` 으로 떨어뜨리지 않는다.
    """
    if condition.op not in _SUPPORTED_OPS:
        raise UnknownOperatorError(f"정의되지 않은 연산자입니다: {condition.op!r}")

    field_value = facts.get(condition.field)
    if field_value is None:
        return ConditionResult(
            id=condition.id,
            label=condition.label,
            state=ConditionState.UNKNOWN,
            required=condition.required,
            evidence=None,
        )

    met = _apply_op(condition.op, field_value, condition.value)
    return ConditionResult(
        id=condition.id,
        label=condition.label,
        state=ConditionState.MET if met else ConditionState.NOT_MET,
        required=condition.required,
        evidence=str(field_value),
    )
