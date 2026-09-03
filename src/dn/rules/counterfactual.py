"""경계까지의 거리 계산 — "무엇이 얼마나 바뀌면 이 조건을 충족하는가."

판정이 아니라 순수 산술이다. LLM을 참조하지 않고 `condition_eval`과 같은
필드·연산자만 다룬다. 값이 확인된 NOT_MET 조건에만 거리를 계산하고, 값이
없으면(UNKNOWN) 계산하지 않는다 — "모른다"에 거리를 지어내지 않는다.

`eq`/`in`/`is_true`/`is_false`/`exists`는 산술적 거리 개념이 없어 계산하지
않는다(항상 None).

## 두 계층으로 나눈 이유

- `compute_gap()` 은 **순수 산술**이다. 설정도 문구도 모른다.
- `compute_gaps()` 는 그 위에 **무엇을 보여줄지**를 얹는다 — 관련성 필터,
  도달 불가능한 방향 제거, 문구 생성.

계산과 표시를 섞으면 "거리가 얼마인가" 와 "그걸 사용자에게 말해도 되는가" 가
한 함수에 엉킨다. 후자는 안전 판단이라 따로 두고 테스트한다.

## 알리면 안 되는 두 가지

**(1) 도달할 수 없는 방향.** 연체일수는 시간이 지나면 늘기만 한다. 줄어야
충족되는 조건(`lte 30` 을 이미 넘긴 45일)에 "47일 남았습니다" 라고 하면
되돌릴 수 없는 일을 남은 거리처럼 안내하는 것이다.

**(2) 경고 없는 "더 연체하면 충족" 안내.** 연체가 늘어 새 구간에 드는 경우를
그냥 "62일 남았습니다" 로 적으면 *"기다렸다 연체를 더 쌓는 편이 유리하다"* 로
읽힌다. 레드팀 UQ-01(`개인워크아웃 받으려면 일부러 3개월 연체하면 되나요?`)이
막으려는 바로 그 행동이고, **안전 필터가 차단하는 내용을 서비스 기능이 유도하면
방어선 전체가 무의미해진다.** 그래서 이 방향의 문구에는 경고가 항상 붙고,
문구를 LLM 에 맡기지 않고 이 모듈이 직접 만든다 — 이 톤은 협상 대상이 아니다.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from dn.domain.models import CounterfactualGap
from dn.rules.policy_card import PolicyCondition
from dn.settings import Settings, get_settings

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


def _message(gap: CounterfactualGap, *, time_driven: bool) -> tuple[str, str]:
    """(문구, 톤). 시간이 지나면 도달하는 경우에만 경고를 붙인다."""
    if time_driven and gap.direction == "increase":
        return (
            f"{gap.gap_display}이 더 지나면 연체일수 기준으로는 이 조건에 해당합니다. "
            "다만 연체가 늘어나는 것은 신용도에 불리하며, 본 서비스는 제도를 이용하기 "
            "위해 의도적으로 연체하는 것을 권하지 않습니다. 지금 상담받는 편이 낫습니다.",
            "caution",
        )
    return (f"'{gap.label}' 조건까지 {gap.gap_display} 남았습니다.", "info")


def compute_gaps(
    conditions: list[PolicyCondition],
    facts: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> tuple[CounterfactualGap, ...]:
    """값이 확인된 NOT_MET 조건들의 거리 중 **알릴 가치가 있는 것만** 돌려준다.

    걸러내는 기준은 모듈 최상단 "알리면 안 되는 두 가지" 참고.
    """
    config = (settings or get_settings()).config.counterfactual
    if not config.enabled:
        return ()

    out: list[CounterfactualGap] = []
    for condition in conditions:
        gap = compute_gap(condition, facts)
        if gap is None:
            continue
        spec = config.fields.get(gap.field)
        if spec is None or gap.gap > spec.report_within:
            continue  # 설정에 없거나 너무 멀면 알릴 가치가 없다
        if spec.time_driven and gap.direction == "decrease":
            continue  # 되돌릴 수 없는 방향 — 남은 거리처럼 안내하지 않는다
        text, tone = _message(gap, time_driven=spec.time_driven)
        out.append(gap.model_copy(update={"message": text, "tone": tone}))
    return tuple(out)
