"""경계까지의 거리 계산 — "무엇이 얼마나 바뀌면 이 조건을 충족하는가."

판정이 아니라 순수 산술이다. LLM을 참조하지 않고 `condition_eval`과 같은
필드·연산자만 다룬다. 값이 확인된 NOT_MET 조건에만 거리를 계산하고, 값이
없으면(UNKNOWN) 계산하지 않는다 — "모른다"에 거리를 지어내지 않는다.

`eq`/`in`/`is_true`/`is_false`/`exists`는 산술적 거리 개념이 없어 계산하지
않는다(항상 None).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from dn.domain.models import CounterfactualGap
from dn.rules.policy_card import PolicyCondition

_DISTANCE_OPS = frozenset({"gte", "gt", "lte", "lt", "between"})


def _as_decimal(x: Any) -> Decimal:
    """정책 카드 YAML의 숫자값은 PyYAML이 `float`로 파싱하는 경우가 있다
    (예: `0.3`). `str()`을 거쳐 이진 부동소수 오차 없이 `Decimal`로 정규화한다.
    """
    return x if isinstance(x, Decimal) else Decimal(str(x))


def _format(field: str, gap: Decimal) -> str:
    if field.endswith("_days"):
        return f"{int(gap)}일"
    if field.endswith("_ratio"):
        return f"{(gap * Decimal('100')):.1f}%p"
    return f"{gap:,}원"


def compute_gap(condition: PolicyCondition, facts: dict[str, Any]) -> CounterfactualGap | None:
    """`condition`이 NOT_MET일 때 충족까지 남은 거리를 계산한다.

    이미 충족됐거나(gap<=0) 필드 값이 없으면 None을 반환한다.
    """
    if condition.op not in _DISTANCE_OPS:
        return None

    field_value = facts.get(condition.field)
    if field_value is None:
        return None

    op = condition.op
    value = _as_decimal(condition.value) if op != "between" else None
    field_value = _as_decimal(field_value)

    if op in ("gte", "gt"):
        gap = value - field_value
        direction = "increase"
    elif op in ("lte", "lt"):
        gap = field_value - value
        direction = "decrease"
    elif op == "between":
        low, high = (_as_decimal(v) for v in condition.value)
        if field_value < low:
            gap = low - field_value
            direction = "increase"
        elif field_value > high:
            gap = field_value - high
            direction = "decrease"
        else:
            return None
    else:  # pragma: no cover - _DISTANCE_OPS 로 이미 필터링됨
        return None

    if gap <= 0:
        return None

    return CounterfactualGap(
        condition_id=condition.id,
        label=condition.label,
        field=condition.field,
        gap=gap,
        gap_display=_format(condition.field, gap),
        direction=direction,
    )


def compute_gaps(
    conditions: list[PolicyCondition], facts: dict[str, Any]
) -> tuple[CounterfactualGap, ...]:
    """조건 목록 중 값이 확인된 NOT_MET 조건들의 거리를 전부 계산한다."""
    gaps = (compute_gap(c, facts) for c in conditions)
    return tuple(g for g in gaps if g is not None)
