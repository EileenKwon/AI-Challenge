"""경계 근접도 — 방향 계산과 의도적 연체 유도 방지."""

from __future__ import annotations

from decimal import Decimal

from dn.domain.enums import ConditionState, PathStatus
from dn.domain.models import ConditionResult, PathCandidate
from dn.rules.proximity import analyze
from dn.settings import get_settings


def _condition(
    cid: str, label: str, field: str, op: str, value, state: ConditionState
) -> ConditionResult:
    return ConditionResult(
        id=cid, label=label, state=state, required=True, field=field, op=op, value=value
    )


def _path(name: str, *conditions: ConditionResult, path_id: str = "p") -> PathCandidate:
    return PathCandidate(
        path_id=path_id,
        name=name,
        priority=1,
        agency="기관",
        status=PathStatus.CANDIDATE,
        met=tuple(c for c in conditions if c.state == ConditionState.MET),
        not_met=tuple(c for c in conditions if c.state == ConditionState.NOT_MET),
    )


def _facts(days: int) -> dict:
    return {"max_overdue_days": days}


def _all_messages(result) -> str:
    return " ".join(b.message for p in result for b in p.boundaries)


# --- 방향 계산 ------------------------------------------------------------------


def test_gte_condition_is_not_lost_by_passing_time() -> None:
    """연체 92일이 개인워크아웃(90일 이상)에서 '2일 뒤 벗어난다'고 하면 안 된다.

    gte 는 값이 내려가야 벗어나는데 연체일수는 시간이 지나면 올라가기만 한다.
    실제로 이 방향을 반대로 계산하는 결함이 있었다.
    """
    path = _path(
        "개인워크아웃",
        _condition("overdue", "연체 90일 이상", "max_overdue_days", "gte", 90, ConditionState.MET),
    )
    assert analyze((path,), _facts(92)) == ()


def test_already_past_upper_bound_is_not_reported_as_reachable() -> None:
    """연체 45일에게 '15일이 더 지나면 30일 이하 구간' 이라고 하면 안 된다."""
    path = _path(
        "신속채무조정",
        _condition(
            "overdue", "연체 30일 이하", "max_overdue_days", "lte", 30, ConditionState.NOT_MET
        ),
    )
    assert analyze((path,), _facts(45)) == ()


def test_upper_bound_met_warns_before_losing_it() -> None:
    path = _path(
        "신속채무조정",
        _condition("overdue", "연체 30일 이하", "max_overdue_days", "lte", 30, ConditionState.MET),
    )
    (result,) = analyze((path,), _facts(28))
    (boundary,) = result.boundaries
    assert boundary.tone == "urgent"
    assert boundary.distance == Decimal("2")
    assert "2일" in boundary.message and "벗어납니다" in boundary.message


# --- 의도적 연체 유도 방지 --------------------------------------------------------


def test_gaining_by_waiting_always_carries_the_warning() -> None:
    """'기다리면 더 좋은 제도가 열린다'로 읽히면 안 된다.

    레드팀 UQ-01(`일부러 3개월 연체하면 되나요?`)이 막으려는 행동을 서비스
    기능이 유도해서는 안 되므로, 이 방향의 문구에는 경고가 반드시 붙는다.
    """
    excluded = _path(
        "개인워크아웃",
        _condition(
            "overdue", "연체 90일 이상", "max_overdue_days", "gte", 90, ConditionState.NOT_MET
        ),
    )
    result = analyze((), _facts(77), excluded_paths=(excluded,))
    (boundary,) = result[0].boundaries

    assert "13일" in boundary.message
    assert "의도적으로 연체하는 것을 권하지 않습니다" in boundary.message
    assert "신용도에 불리" in boundary.message
    assert boundary.tone != "urgent"  # 기회처럼 강조하지 않는다


def test_excluded_paths_are_included() -> None:
    """가장 알릴 가치가 큰 경우가 제외 경로에 있다 — 누락된 적이 있었다."""
    excluded = _path(
        "개인워크아웃",
        _condition(
            "overdue", "연체 90일 이상", "max_overdue_days", "gte", 90, ConditionState.NOT_MET
        ),
    )
    assert analyze((), _facts(77), excluded_paths=(excluded,)) != ()


# --- 중복 제거 --------------------------------------------------------------------


def test_same_condition_id_with_different_thresholds_is_kept() -> None:
    """카드마다 조건 id 가 같아도(overdue_range) 임계치가 다르면 별개 사실이다.

    id 만으로 묶으면 '13일 뒤 개인워크아웃 구간' 이 사라진다 — 실제로 사라졌었다.
    """
    a = _path(
        "사전채무조정",
        _condition(
            "overdue_range", "31~89일", "max_overdue_days", "between", [31, 89], ConditionState.MET
        ),
        path_id="pre",
    )
    b = _path(
        "개인워크아웃",
        _condition(
            "overdue_range", "90일 이상", "max_overdue_days", "gte", 90, ConditionState.NOT_MET
        ),
        path_id="workout",
    )
    result = analyze((a,), _facts(77), excluded_paths=(b,))
    assert {p.path_name for p in result} == {"사전채무조정", "개인워크아웃"}


def test_identical_condition_reported_once() -> None:
    same = lambda: _condition(  # noqa: E731
        "overdue", "연체 30일 이하", "max_overdue_days", "lte", 30, ConditionState.MET
    )
    a = _path("제도A", same(), path_id="a")
    b = _path("제도B", same(), path_id="b")
    result = analyze((a, b), _facts(28))
    assert sum(len(p.boundaries) for p in result) == 1


# --- 보고 범위 --------------------------------------------------------------------


def test_distance_beyond_threshold_is_silent() -> None:
    """총채무 한도까지 14억 남았다는 안내는 사용자에게 쓸모가 없다."""
    path = _path(
        "제도",
        _condition(
            "overdue", "연체 30일 이하", "max_overdue_days", "lte", 30, ConditionState.NOT_MET
        ),
    )
    assert analyze((path,), _facts(500)) == ()


def test_field_absent_from_config_is_silent() -> None:
    path = _path(
        "제도",
        _condition("cap", "총 채무 15억 이하", "total_debt", "lte", 1500000000, ConditionState.MET),
    )
    assert analyze((path,), {"total_debt": Decimal("1499999999")}) == ()


def test_disabled_by_config() -> None:
    base = get_settings()
    off = base.model_copy(
        update={
            "config": base.config.model_copy(
                update={"proximity": base.config.proximity.model_copy(update={"enabled": False})}
            )
        }
    )
    path = _path(
        "제도",
        _condition("overdue", "연체 30일 이하", "max_overdue_days", "lte", 30, ConditionState.MET),
    )
    assert analyze((path,), _facts(28), settings=off) == ()
