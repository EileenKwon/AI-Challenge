"""T12 — 규칙 엔진 테스트.

연체일수 경계값 29/30/31/89/90 각각에서 기대 경로가 CANDIDATE 로 나오는지,
소득증빙 미확인이 EXCLUDED 가 아니라 NEEDS_INFO 로 분류되는지, 반환 경로 수가
3을 넘지 않는지를 검증한다.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from dn.domain.enums import PathStatus
from dn.rules.engine import evaluate
from dn.rules.policy_card import load_usable_cards


def _base_facts(**overrides):
    facts = {
        "max_overdue_days": 0,
        "total_debt": Decimal("10000000"),
        # 신복위 제도는 총액과 별도로 담보/무담보 한도를 규정하므로 함께 채운다.
        "unsecured_debt": Decimal("10000000"),
        "secured_debt": Decimal("0"),
        # 최근 6개월 신규채무 원금 비율 — 제도 공통 조건(30% 미만).
        "recent_debt_ratio": Decimal("0.10"),
        "has_continuous_income": True,
        "income_proof_available": True,
        "has_secured_debt": False,
        "has_overdue": False,
        "income_drop_signal": False,
        "court_proceeding_ongoing": False,
        "seizure_ongoing": False,
        "has_guarantee_debt": False,
        "has_tax_debt": False,
        "has_private_debt": False,
    }
    facts.update(overrides)
    return facts


def _path_by_id(result, path_id: str):
    for p in result.paths:
        if p.path_id == path_id:
            return p
    for p in result.excluded_paths:
        if p.path_id == path_id:
            return p
    return None


@pytest.fixture(scope="module")
def cards():
    usable, _ = load_usable_cards()
    return usable


# --- 연체일수 경계값 ------------------------------------------------------------


@pytest.mark.parametrize(
    "overdue_days,expected_candidate,expected_excluded",
    [
        (29, "sinsok_debt_adjustment", "pre_debt_adjustment"),
        (30, "sinsok_debt_adjustment", "pre_debt_adjustment"),
        (31, "pre_debt_adjustment", "sinsok_debt_adjustment"),
        (89, "pre_debt_adjustment", "personal_workout"),
        (90, "personal_workout", "pre_debt_adjustment"),
    ],
)
def test_overdue_boundary_selects_expected_bracket(
    cards, overdue_days, expected_candidate, expected_excluded
) -> None:
    facts = _base_facts(max_overdue_days=overdue_days)
    result = evaluate(facts, cards)

    candidate_path = _path_by_id(result, expected_candidate)
    assert candidate_path is not None
    assert candidate_path.status == PathStatus.CANDIDATE

    excluded_path = _path_by_id(result, expected_excluded)
    assert excluded_path is not None
    assert excluded_path.status == PathStatus.EXCLUDED


# --- 소득증빙 미확인 → NEEDS_INFO (EXCLUDED 아님) --------------------------------


def test_unknown_income_proof_yields_needs_info_not_excluded(cards) -> None:
    facts = _base_facts(max_overdue_days=42, income_proof_available=None)
    result = evaluate(facts, cards)

    pre_debt = _path_by_id(result, "pre_debt_adjustment")
    assert pre_debt is not None
    assert pre_debt.status == PathStatus.NEEDS_INFO
    assert any(u.id == "income_proof" for u in pre_debt.unknown)


def test_unknown_continuous_income_yields_needs_info_not_excluded(cards) -> None:
    facts = _base_facts(max_overdue_days=15, has_continuous_income=None)
    result = evaluate(facts, cards)

    sinsok = _path_by_id(result, "sinsok_debt_adjustment")
    assert sinsok is not None
    assert sinsok.status == PathStatus.NEEDS_INFO


# --- 제외 조건 ------------------------------------------------------------------


def test_court_proceeding_excludes_committee_programs(cards) -> None:
    facts = _base_facts(max_overdue_days=42, court_proceeding_ongoing=True)
    result = evaluate(facts, cards)

    pre_debt = _path_by_id(result, "pre_debt_adjustment")
    assert pre_debt is not None
    assert pre_debt.status == PathStatus.EXCLUDED


# --- 반환 경로 수 제한 -----------------------------------------------------------


def test_returned_paths_never_exceed_three(cards) -> None:
    facts = _base_facts(max_overdue_days=42)
    result = evaluate(facts, cards)
    assert len(result.paths) <= 3


# --- 판정 불가(undetermined) ----------------------------------------------------


def test_missing_max_overdue_days_marks_undetermined(cards) -> None:
    facts = _base_facts(max_overdue_days=None)
    result = evaluate(facts, cards)
    assert result.undetermined is True
    assert any("연체일수" in r for r in result.undetermined_reasons)


def test_no_cards_marks_undetermined_and_empty_paths() -> None:
    result = evaluate(_base_facts(), [])
    assert result.undetermined is True
    assert result.paths == ()


def test_unresolved_conflicts_marks_undetermined(cards) -> None:
    result = evaluate(_base_facts(max_overdue_days=42), cards, has_unresolved_conflicts=True)
    assert result.undetermined is True


def test_fully_known_facts_are_not_undetermined(cards) -> None:
    result = evaluate(_base_facts(max_overdue_days=42), cards)
    assert result.undetermined is False


# --- 반사실 거리(counterfactual_gaps) --------------------------------------------


def test_excluded_path_carries_counterfactual_gap(cards) -> None:
    facts = _base_facts(max_overdue_days=89)
    result = evaluate(facts, cards)

    personal_workout = _path_by_id(result, "personal_workout")
    assert personal_workout is not None
    assert personal_workout.status == PathStatus.EXCLUDED

    overdue_gap = next(
        g for g in personal_workout.counterfactual_gaps if g.field == "max_overdue_days"
    )
    assert overdue_gap.gap == Decimal("1")
    assert overdue_gap.direction == "increase"
    assert overdue_gap.gap_display == "1일"


def test_candidate_path_has_no_counterfactual_gap(cards) -> None:
    """CANDIDATE 는 NOT_MET 조건이 없으므로 거리도 없다."""
    facts = _base_facts(max_overdue_days=90)
    result = evaluate(facts, cards)

    personal_workout = _path_by_id(result, "personal_workout")
    assert personal_workout is not None
    assert personal_workout.status == PathStatus.CANDIDATE
    assert personal_workout.counterfactual_gaps == ()


# --- dev_mode 전달 ---------------------------------------------------------------


def test_dev_mode_flag_is_passed_through(cards) -> None:
    result = evaluate(_base_facts(max_overdue_days=42), cards, dev_mode=True)
    assert result.dev_mode is True
