"""T22 — 설명가능성 번들 테스트.

결과에 등장하는 모든 숫자가 calc_trace 또는 입력값으로 역추적되는지,
GET /explain 이 기획서 10.1 (4) 의 8개 항목을 모두 반환하는지 확인한다.
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from dn.api.deps import get_session_store
from dn.domain.enums import FieldSource, ProductType, SessionStage
from dn.domain.models import Debt, ExtractionResult, HouseholdProfile, IncomeProfile, SessionState
from dn.domain.provenance import Tracked
from dn.main import create_app
from dn.pipeline.orchestrator import analyze

_NUMBER_RE = re.compile(r"-?[\d,]+(?:\.\d+)?")


def _known(value):
    return Tracked(value=value, source=FieldSource.DOCUMENT)


def _kimhaneul_state() -> SessionState:
    debts = (
        Debt(
            debt_id="d0",
            creditor=_known("A금융"),
            product_type=_known(ProductType.CREDIT_LOAN),
            balance=_known(Decimal("25000000")),
            overdue_days=_known(42),
            is_secured=_known(False),
            monthly_payment=_known(Decimal("620000")),
        ),
        Debt(
            debt_id="d1",
            creditor=_known("B카드"),
            product_type=_known(ProductType.CARD_LOAN),
            balance=_known(Decimal("14000000")),
            overdue_days=_known(0),
            is_secured=_known(False),
            monthly_payment=_known(Decimal("380000")),
        ),
    )
    now = datetime(2026, 8, 18)
    return SessionState(
        session_id="explain-test",
        stage=SessionStage.S4_SUPPLEMENTED,
        created_at=now,
        updated_at=now,
        extraction=ExtractionResult(debts=debts),
        income=IncomeProfile(
            monthly_net_income=_known(Decimal("2500000")), has_continuous_income=_known(True)
        ),
        household=HouseholdProfile(essential_living_cost=_known(Decimal("1450000"))),
    )


def _numbers_in(text: str) -> set[str]:
    return set(_NUMBER_RE.findall(text))


def test_every_cashflow_number_is_traceable_via_calc_trace_or_inputs() -> None:
    state = _kimhaneul_state()
    result = analyze(state)
    cashflow = result.cashflow
    assert cashflow is not None

    trace_text = " ".join(
        f"{step.formula} {step.output} {' '.join(step.inputs.values())}" for step in cashflow.trace
    )
    input_text = " ".join(
        [
            str(state.income.monthly_net_income.value),
            str(state.household.essential_living_cost.value),
        ]
        + [str(d.monthly_payment.value) for d in state.extraction.debts]
        + [str(d.balance.value) for d in state.extraction.debts]
    )
    traceable_numbers = _numbers_in(trace_text) | _numbers_in(input_text)

    for field in ("total_debt", "monthly_total_payment", "monthly_available", "monthly_shortfall"):
        value = getattr(cashflow, field)
        formatted = f"{value:,}"
        assert formatted in traceable_numbers or str(value) in traceable_numbers, (
            f"{field}={value} 를 trace/입력값에서 역추적할 수 없음"
        )


def test_explain_endpoint_returns_eight_items() -> None:
    client = TestClient(create_app())
    state = _kimhaneul_state()
    get_session_store().create(state)

    result = analyze(state)
    new_state = state.model_copy(update={"stage": SessionStage.S5_ANALYZED, "analysis": result})
    get_session_store().save(new_state)

    response = client.get(f"/api/session/{state.session_id}/explain")
    assert response.status_code == 200
    body = response.json()

    expected_keys = {
        "사용자_입력값",
        "AI_추출값",
        "사용자_수정_이력",
        "적용된_규칙과_버전",
        "계산_trace",
        "LLM_생성문",
        "공식_근거와_기준일",
        "미확인_항목",
    }
    assert expected_keys == set(body.keys())
    assert len(body["계산_trace"]) >= 3
    assert body["공식_근거와_기준일"]["policy_base_date"] is not None


def test_explain_returns_404_before_analysis() -> None:
    client = TestClient(create_app())
    state = _kimhaneul_state()
    get_session_store().create(state)

    response = client.get(f"/api/session/{state.session_id}/explain")
    assert response.status_code == 404


def test_rule_version_is_populated_not_empty() -> None:
    result = analyze(_kimhaneul_state())
    assert result.rules is not None
    assert result.rules.rule_version != ""


def test_edit_history_reflects_user_edited_fields() -> None:
    state = _kimhaneul_state()
    edited_debt = state.extraction.debts[0].model_copy(
        update={
            "creditor": Tracked(
                value="A금융(수정됨)",
                source=FieldSource.USER_EDIT,
                edited_at=datetime(2026, 8, 18, 10, 0, 0),
            )
        }
    )
    new_extraction = state.extraction.model_copy(
        update={"debts": (edited_debt, *state.extraction.debts[1:])}
    )
    state = state.model_copy(update={"extraction": new_extraction})

    result = analyze(state)
    assert len(result.edit_history) == 1
    assert "debt_0.creditor" in result.edit_history[0]
