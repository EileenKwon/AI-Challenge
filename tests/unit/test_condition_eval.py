"""T11 — 3-state 조건 평가기 테스트. 연산자 10종 × (MET/NOT_MET/UNKNOWN)."""

from __future__ import annotations

import pytest

from dn.domain.enums import ConditionState
from dn.rules.condition_eval import UnknownOperatorError, evaluate
from dn.rules.policy_card import PolicyCondition


def _cond(op: str, value=None, field: str = "f") -> PolicyCondition:
    return PolicyCondition(id="c", label="l", field=field, op=op, value=value, required=True)


# --- 연산자 10종 × 3-state ------------------------------------------------------


@pytest.mark.parametrize(
    "op,value,met_facts,not_met_facts",
    [
        ("between", [10, 20], {"f": 15}, {"f": 25}),
        ("lte", 20, {"f": 15}, {"f": 25}),
        ("gte", 10, {"f": 15}, {"f": 5}),
        ("lt", 20, {"f": 15}, {"f": 25}),
        ("gt", 10, {"f": 15}, {"f": 5}),
        ("eq", "x", {"f": "x"}, {"f": "y"}),
        ("in", ["a", "b", "c"], {"f": "b"}, {"f": "z"}),
        ("is_true", None, {"f": True}, {"f": False}),
        ("is_false", None, {"f": False}, {"f": True}),
    ],
)
def test_operator_met_not_met_unknown(op, value, met_facts, not_met_facts) -> None:
    condition = _cond(op, value)

    met = evaluate(condition, met_facts)
    assert met.state == ConditionState.MET

    not_met = evaluate(condition, not_met_facts)
    assert not_met.state == ConditionState.NOT_MET

    unknown_missing = evaluate(condition, {})
    assert unknown_missing.state == ConditionState.UNKNOWN

    unknown_none = evaluate(condition, {"f": None})
    assert unknown_none.state == ConditionState.UNKNOWN


def test_exists_operator_met_and_unknown() -> None:
    """exists 는 부재를 UNKNOWN 으로 흡수하므로 evaluate() 를 통해서는 NOT_MET 이 나오지 않는다."""
    condition = _cond("exists")

    assert evaluate(condition, {"f": "anything"}).state == ConditionState.MET
    assert evaluate(condition, {"f": 0}).state == ConditionState.MET  # 0 은 None 이 아니다
    assert evaluate(condition, {"f": False}).state == ConditionState.MET  # False 도 None 이 아니다
    assert evaluate(condition, {}).state == ConditionState.UNKNOWN
    assert evaluate(condition, {"f": None}).state == ConditionState.UNKNOWN


# --- None 입력이 NOT_MET 으로 떨어지지 않음 -------------------------------------


@pytest.mark.parametrize(
    "op,value",
    [
        ("between", [10, 20]),
        ("lte", 20),
        ("gte", 10),
        ("lt", 20),
        ("gt", 10),
        ("eq", "x"),
        ("in", ["a", "b"]),
        ("is_true", None),
        ("is_false", None),
        ("exists", None),
    ],
)
def test_missing_or_none_never_becomes_not_met(op, value) -> None:
    condition = _cond(op, value)
    assert evaluate(condition, {}).state != ConditionState.NOT_MET
    assert evaluate(condition, {"f": None}).state != ConditionState.NOT_MET
    assert evaluate(condition, {}).state == ConditionState.UNKNOWN
    assert evaluate(condition, {"f": None}).state == ConditionState.UNKNOWN


# --- 알 수 없는 연산자 -----------------------------------------------------------


def test_unknown_operator_raises_instead_of_silently_false() -> None:
    condition = _cond("regex_match", "foo")
    with pytest.raises(UnknownOperatorError):
        evaluate(condition, {"f": "foo"})


def test_no_eval_or_exec_used_in_module() -> None:
    import ast
    import inspect

    from dn.rules import condition_eval

    tree = ast.parse(inspect.getsource(condition_eval))
    call_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "eval" not in call_names
    assert "exec" not in call_names


# --- required/evidence 전달 -----------------------------------------------------


def test_result_carries_condition_metadata() -> None:
    condition = PolicyCondition(
        id="overdue_range",
        label="연체일수 구간",
        field="max_overdue_days",
        op="between",
        value=[31, 89],
        required=True,
    )
    result = evaluate(condition, {"max_overdue_days": 42})
    assert result.id == "overdue_range"
    assert result.label == "연체일수 구간"
    assert result.required is True
    assert result.state == ConditionState.MET
    assert result.evidence == "42"
