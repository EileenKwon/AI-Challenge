"""T07 — 3단계 질문(고정 + 조건부 3문항) 테스트.

고정 문항 개수는 매직 넘버로 고정하지 않는다. 정책 카드가 요구하는 사실이
늘면 문항도 늘어야 하는데, 개수를 상수로 박아두면 그 변경이 곧 테스트 실패가
되어 "질문을 추가하지 말라"는 테스트가 되어버린다. 대신 구성(어떤 qid 가
있는지)과 관계(고정 + 트리거된 조건부)를 검사한다.
"""

from __future__ import annotations

from dn.domain.enums import FieldSource
from dn.domain.models import Debt, SituationFlags
from dn.domain.provenance import Tracked
from dn.reconcile.questions import (
    has_income_drop_signal,
    has_overdue,
    has_secured_debt,
    load_conditional_questions,
    load_fixed_questions,
    select_active_questions,
)

# 정책 카드 조건 평가에 반드시 필요한 사실을 묻는 문항들.
# 이 중 하나라도 빠지면 해당 조건이 영구 UNKNOWN 이 되어 제도가 NEEDS_INFO 에 갇힌다.
_REQUIRED_QIDS = {
    "Q1_INCOME",  # monthly_net_income
    "Q2_LIVING_COST",  # essential_living_cost
    "Q3_INCOME_PROOF",  # income_proof_available
    "Q6_CONTINUOUS_INCOME",  # has_continuous_income — 신복위 제도 공통 요건
}


def test_fixed_questions_cover_all_policy_required_facts() -> None:
    qids = {q.qid for q in load_fixed_questions()}
    missing = _REQUIRED_QIDS - qids
    assert not missing, f"정책 조건 평가에 필요한 문항이 없습니다: {missing}"


def test_fixed_questions_have_unique_ids() -> None:
    qids = [q.qid for q in load_fixed_questions()]
    assert len(qids) == len(set(qids))


def test_exactly_three_conditional_questions() -> None:
    assert len(load_conditional_questions()) == 3


def test_select_active_questions_without_triggers_returns_only_fixed() -> None:
    active = select_active_questions(
        secured_debt_present=False, overdue_present=False, income_drop_present=False
    )
    assert len(active) == len(load_fixed_questions())


def test_select_active_questions_with_all_triggers_adds_all_conditional() -> None:
    active = select_active_questions(
        secured_debt_present=True, overdue_present=True, income_drop_present=True
    )
    assert len(active) == len(load_fixed_questions()) + len(load_conditional_questions())


def test_select_active_questions_with_one_trigger_adds_one() -> None:
    active = select_active_questions(
        secured_debt_present=True, overdue_present=False, income_drop_present=False
    )
    assert len(active) == len(load_fixed_questions()) + 1
    assert any(q.qid == "C1_COLLATERAL" for q in active)


def test_has_secured_debt_detects_true_flag() -> None:
    secured = Debt(debt_id="d0", is_secured=Tracked(value=True, source=FieldSource.DOCUMENT))
    unsecured = Debt(debt_id="d1", is_secured=Tracked(value=False, source=FieldSource.DOCUMENT))
    assert has_secured_debt((secured, unsecured)) is True
    assert has_secured_debt((unsecured,)) is False


def test_has_overdue_detects_positive_days() -> None:
    overdue = Debt(debt_id="d0", overdue_days=Tracked(value=10, source=FieldSource.DOCUMENT))
    not_overdue = Debt(debt_id="d1", overdue_days=Tracked(value=0, source=FieldSource.DOCUMENT))
    assert has_overdue((overdue,)) is True
    assert has_overdue((not_overdue,)) is False


def test_has_income_drop_signal_from_job_loss_or_business_closed() -> None:
    job_loss = SituationFlags(recent_job_loss=Tracked(value=True, source=FieldSource.USER_INPUT))
    neither = SituationFlags()
    assert has_income_drop_signal(job_loss) is True
    assert has_income_drop_signal(neither) is False
