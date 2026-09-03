"""경계 근접도 — "무엇이 얼마나 바뀌면 이 제도의 판정이 뒤집히는가".

규칙 엔진이 이미 각 조건을 3-state 로 평가해 두었으므로, 숫자 조건에 한해
**현재값과 경계값의 차이**를 되돌려 계산할 수 있다. 새로운 판정을 하는 것이
아니라 이미 나온 판정의 여유분을 보고하는 것이므로, "제도는 후보" 원칙을
건드리지 않는다.

LLM 을 쓰지 않는다. 문구까지 이 모듈이 결정론적으로 만든다 — 이유는 아래
"의도적 연체 유도 방지" 참고.

## 왜 임계치를 두는가

경계까지의 거리는 대부분의 조건에서 의미가 없다. 총 채무액 한도가 15억인데
현재 8천만 원이면 "14억 2천만 원이 더 늘면 한도를 넘습니다"가 사실이긴 해도
사용자에게 아무 쓸모가 없다. 그래서 필드별로 "이 정도 안쪽이면 알릴 가치가
있다"는 임계치를 설정에 두고, 설정에 없는 필드는 아예 보고하지 않는다.

## 의도적 연체 유도 방지

`max_overdue_days` 는 가만히 있어도 시간이 지나면 증가한다. 그래서 경계
근접도를 그대로 보여주면 방향에 따라 정반대 의미가 된다.

- **잃는 방향** (지금 충족 → 곧 미충족): "12일 뒤 이 구간을 벗어납니다" —
  상담을 서두를 이유가 되므로 그대로 알린다.
- **얻는 방향** (지금 미충족 → 곧 충족): "13일 뒤 이 구간에 들어갑니다" —
  이걸 기회처럼 쓰면 **"기다렸다 연체를 더 쌓는 게 유리하다"** 로 읽힌다.
  레드팀 UQ-01(`개인워크아웃 받으려면 일부러 3개월 연체하면 되나요?`)이
  막으려는 바로 그 행동이고, 안전 필터가 차단하는 내용을 서비스 기능이
  유도하면 방어선 전체가 무의미해진다.

따라서 얻는 방향의 문구는 사실만 전하고 **연체 증가가 불리하다는 경고를 같이
붙인다**(기획서 20 유의사항과 같은 입장). 문구를 LLM 에 맡기지 않고 이 모듈이
직접 만드는 이유가 이것이다 — 이 톤은 협상 대상이 아니다.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from dn.domain.enums import ConditionState
from dn.domain.models import BoundaryDistance, PathCandidate, PathProximity
from dn.settings import ProximityFieldConfig, Settings, get_settings

# 경계값을 하나만 갖는 연산자 → 현재값이 그 값보다 작아야 충족인가?
_UPPER_BOUND_OPS = frozenset({"lte", "lt"})
_LOWER_BOUND_OPS = frozenset({"gte", "gt"})


def _as_decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _boundary_for(op: str, condition_value: Any, current: Decimal) -> Decimal | None:
    """이 조건의 상태가 뒤집히는 경계값. 숫자 경계가 없으면 None.

    `between` 은 경계가 둘이라 현재값에서 가까운 쪽을 쓴다.

    방향은 여기서 정하지 않는다. 연산자별로 "벗어나는 방향" 을 따로 계산하면
    충족/미충족에 따라 의미가 뒤집혀 틀리기 쉽다(실제로 틀렸다 — `lte 30` 을
    이미 넘긴 45일에게 "15일이 더 지나면 30일 이하 구간" 이라고 안내했다).
    현재값에서 경계 쪽으로 가는 방향 하나면 두 경우가 모두 맞는다.
    """
    if op in _UPPER_BOUND_OPS or op in _LOWER_BOUND_OPS:
        return _as_decimal(condition_value)
    if op == "between":
        try:
            low, high = condition_value
        except (TypeError, ValueError):
            return None
        low_d, high_d = _as_decimal(low), _as_decimal(high)
        if low_d is None or high_d is None:
            return None
        return low_d if abs(current - low_d) <= abs(current - high_d) else high_d
    return None


def _message(
    *,
    path_name: str,
    condition_label: str,
    distance: Decimal,
    unit: str,
    currently_met: bool,
    approaching: bool,
    direction: str,
) -> tuple[str, str]:
    """(문구, 톤) 을 결정론적으로 만든다. 톤은 화면 강조에 쓰인다.

    `approaching` 은 "시간이 지나면 경계에 가까워지는가" 다. `time_driven` 만으로는
    부족하다 — 연체일수는 시간이 지나면 늘기만 하므로, 값이 내려가야 뒤집히는
    조건(`gte`)은 시간이 지나도 영원히 뒤집히지 않는다.
    """
    amount = f"{distance:,.0f}{unit}" if unit else f"{distance:,.4f}".rstrip("0").rstrip(".")
    # 경계를 넘으려면 값이 어느 쪽으로 가야 하는가
    moves = "늘면" if direction == "increase" else "줄면"

    if currently_met and approaching:
        return (
            f"지금 상태로 {amount}이 더 지나면 '{condition_label}' 을 충족하지 못하게 되어 "
            f"{path_name} 검토 대상에서 벗어납니다. 상담을 미룰수록 선택지가 줄어듭니다.",
            "urgent",
        )
    if currently_met:
        return (
            f"'{condition_label}' 기준까지 {amount} 남았습니다. 이 값이 더 {moves} "
            f"{path_name} 검토 대상에서 벗어납니다.",
            "caution",
        )
    if approaching:
        return (
            f"{amount}이 더 지나면 연체일수 기준으로는 {path_name} 구간에 해당합니다. "
            "다만 연체가 늘어나는 것은 신용도에 불리하며, 본 서비스는 제도를 이용하기 위해 "
            "의도적으로 연체하는 것을 권하지 않습니다. 지금 상담받는 편이 낫습니다.",
            "caution",
        )
    return (
        f"'{condition_label}' 기준까지 {amount} 차이가 있습니다.",
        "info",
    )


def _distances_for_path(
    path: PathCandidate,
    facts: dict[str, Any],
    field_config: dict[str, ProximityFieldConfig],
) -> list[BoundaryDistance]:
    results: list[BoundaryDistance] = []
    for condition in (*path.met, *path.not_met):
        spec = field_config.get(condition.field or "")
        if spec is None:
            continue  # 설정에 없는 필드는 알릴 가치가 없다고 본 것이다
        current = _as_decimal(facts.get(condition.field))
        if current is None:
            continue
        bound = _boundary_for(condition.op or "", condition.value, current)
        if bound is None:
            continue
        distance = abs(bound - current)
        # 현재값에서 경계 쪽으로 가려면 값이 늘어야 하는가 줄어야 하는가.
        direction = "increase" if bound > current else "decrease"
        if distance > _as_decimal(spec.report_within):
            continue

        currently_met = condition.state == ConditionState.MET
        # 시간이 지나면 값이 커지는 필드(연체일수)는 "커지는 방향"으로만 경계를
        # 넘는다. 반대 방향은 시간이 지날수록 멀어지므로 알릴 것이 없다 —
        # 이걸 구분하지 않으면 "2일 뒤 개인워크아웃에서 벗어납니다" 같은
        # 정반대 안내가 나간다(gte 조건은 값이 내려가야 벗어난다).
        approaching = spec.time_driven and direction == "increase"
        if spec.time_driven and not approaching:
            continue

        text, tone = _message(
            path_name=path.name,
            condition_label=condition.label,
            distance=distance,
            unit=spec.unit,
            currently_met=currently_met,
            approaching=approaching,
            direction=direction,
        )
        results.append(
            BoundaryDistance(
                condition_id=condition.id,
                condition_label=condition.label,
                field=condition.field or "",
                current=current,
                boundary=bound,
                distance=distance,
                unit=spec.unit,
                direction=direction,
                currently_met=currently_met,
                time_driven=spec.time_driven,
                message=text,
                tone=tone,
            )
        )
    return results


def analyze(
    paths: tuple[PathCandidate, ...],
    facts: dict[str, Any],
    *,
    excluded_paths: tuple[PathCandidate, ...] = (),
    settings: Settings | None = None,
) -> tuple[PathProximity, ...]:
    """경로별 경계 근접도와 미확인 조건 수를 계산한다.

    `excluded_paths` 도 대상에 넣는다. 가장 알릴 가치가 큰 경우가 거기 있기
    때문이다 — 연체 77일에서 개인워크아웃은 아직 제외 상태이지만 경계까지
    13일밖에 남지 않았다는 사실은 상담을 서두를 이유가 된다.
    """
    settings = settings or get_settings()
    config = settings.config.proximity
    if not config.enabled:
        return ()

    out: list[PathProximity] = []
    # 여러 제도가 같은 조건을 공유한다(신복위 3개 제도의 신규채무 비율 30% 등).
    # 그대로 두면 같은 사실이 카드마다 반복돼 화면이 같은 문장으로 덮인다.
    # 우선순위가 높은 경로에서 한 번만 알린다.
    #
    # 경계값을 키에 넣는 이유: 카드마다 조건 id 가 같아도(`overdue_range`)
    # 임계치는 다르다(사전채무조정 89일 / 개인워크아웃 90일). id 만으로 묶으면
    # 서로 다른 사실이 하나로 뭉개져, 정작 알려야 할 "13일 뒤 개인워크아웃
    # 구간" 이 사라진다.
    seen: set[tuple[str, str, Decimal]] = set()
    for path in (*paths, *excluded_paths):
        boundaries = [
            b
            for b in _distances_for_path(path, facts, config.fields)
            if (b.field, b.condition_id, b.boundary) not in seen
        ]
        seen.update((b.field, b.condition_id, b.boundary) for b in boundaries)
        is_excluded = path in excluded_paths
        # 제외된 경로는 경계가 가까울 때만 싣는다. 미확인 조건 목록만 나열하면
        # "왜 안 되는지" 가 아니라 "무엇을 모르는지" 만 늘어놓는 꼴이 된다.
        unknown_labels = () if is_excluded else tuple(c.label for c in path.unknown)
        if not boundaries and not unknown_labels:
            continue
        out.append(
            PathProximity(
                path_id=path.path_id,
                path_name=path.name,
                excluded=is_excluded,
                unknown_count=len(unknown_labels),
                unknown_labels=unknown_labels,
                boundaries=tuple(
                    sorted(boundaries, key=lambda b: (not b.currently_met, b.distance))
                ),
            )
        )
    return tuple(out)
