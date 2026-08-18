"""보완입력 · 분석 · 계획 · 요약서 라우터. 비즈니스 로직은 각 모듈에 있다."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from dn.api.deps import get_llm_client_dep, get_session_or_404, get_session_store
from dn.domain.enums import FieldSource, SessionStage
from dn.domain.models import (
    ExtractionResult,
    HouseholdProfile,
    IncomeProfile,
    ReportOptions,
    SituationFlags,
)
from dn.domain.provenance import Tracked
from dn.llm.client import LLMClient
from dn.pipeline.orchestrator import analyze as run_analysis
from dn.pipeline.stages import transition
from dn.planning.action_plan import build_plan
from dn.reconcile.conflict_detector import detect_conflicts
from dn.reconcile.gap_detector import detect_gaps
from dn.reconcile.questions import (
    has_income_drop_signal,
    has_overdue,
    has_secured_debt,
    select_active_questions,
)
from dn.report.summary_pdf import render as render_summary
from dn.storage.session_store import SessionStore

router = APIRouter(prefix="/api/session", tags=["analysis"])


@router.get("/{session_id}/gaps")
def get_gaps(session_id: str, store: SessionStore = Depends(get_session_store)) -> dict:
    state = get_session_or_404(session_id, store)
    extraction = state.extraction or ExtractionResult()
    gaps = detect_gaps(extraction.debts, state.income)
    conflicts = detect_conflicts(extraction, state.household)
    questions = select_active_questions(
        secured_debt_present=has_secured_debt(extraction.debts),
        overdue_present=has_overdue(extraction.debts),
        income_drop_present=has_income_drop_signal(state.flags),
    )
    return {
        "gaps": [g.model_dump() for g in gaps.gaps],
        "conflicts": [c.model_dump() for c in conflicts.conflicts],
        "questions": [q.model_dump() for q in questions],
    }


class DebtFinancialUpdate(BaseModel):
    """04 화면의 채무별 금리·월상환액 입력 — 조회서에 없는 보완 입력 대상(기획서 2.2)."""

    debt_index: int
    interest_rate_percent: Decimal | None = None  # 사용자 입력은 %, 저장은 0~1 비율로 환산
    monthly_payment: Decimal | None = None
    skip: bool = False


class SupplementRequest(BaseModel):
    monthly_net_income: Decimal | None = None
    support_income: Decimal | None = None
    income_proof_available: bool | None = None
    essential_living_cost: Decimal | None = None
    housing_cost: Decimal | None = None
    medical_care_cost: Decimal | None = None
    other_fixed_cost: Decimal | None = None
    dependents: int | None = None
    has_collateral_asset: bool | None = None  # C1_COLLATERAL
    under_collection_contact: bool | None = None  # C2_COLLECTION
    income_drop_occurred: bool | None = None  # C3_INCOME_DROP
    debts: list[DebtFinancialUpdate] | None = None


def _apply_supplement_income(income: IncomeProfile, body: SupplementRequest) -> IncomeProfile:
    update = {}
    for field_name in ("monthly_net_income", "support_income", "income_proof_available"):
        value = getattr(body, field_name)
        if value is not None:
            update[field_name] = Tracked(value=value, source=FieldSource.USER_INPUT)
    return income.model_copy(update=update) if update else income


def _apply_supplement_household(
    household: HouseholdProfile, body: SupplementRequest
) -> HouseholdProfile:
    update = {}
    for field_name in (
        "essential_living_cost",
        "housing_cost",
        "medical_care_cost",
        "other_fixed_cost",
        "dependents",
    ):
        value = getattr(body, field_name)
        if value is not None:
            update[field_name] = Tracked(value=value, source=FieldSource.USER_INPUT)
    return household.model_copy(update=update) if update else household


def _apply_supplement_debts(
    extraction: ExtractionResult, body: SupplementRequest
) -> ExtractionResult:
    if not body.debts:
        return extraction
    debts = list(extraction.debts)
    for item in body.debts:
        if item.skip or item.debt_index >= len(debts):
            continue
        debt = debts[item.debt_index]
        update = {}
        if item.interest_rate_percent is not None:
            update["interest_rate"] = Tracked(
                value=item.interest_rate_percent / Decimal("100"),
                source=FieldSource.USER_INPUT,
            )
        if item.monthly_payment is not None:
            update["monthly_payment"] = Tracked(
                value=item.monthly_payment, source=FieldSource.USER_INPUT
            )
        if update:
            debts[item.debt_index] = debt.model_copy(update=update)
    return extraction.model_copy(update={"debts": tuple(debts)})


def _apply_supplement_flags(flags: SituationFlags, body: SupplementRequest) -> SituationFlags:
    update = {}
    if body.has_collateral_asset is not None:
        tracked = Tracked(value=body.has_collateral_asset, source=FieldSource.USER_INPUT)
        update["has_real_estate"] = tracked
        update["has_vehicle"] = tracked
        update["has_lease_deposit"] = tracked
    if body.under_collection_contact is not None:
        update["under_collection_contact"] = Tracked(
            value=body.under_collection_contact, source=FieldSource.USER_INPUT
        )
    if body.income_drop_occurred is not None:
        tracked = Tracked(value=body.income_drop_occurred, source=FieldSource.USER_INPUT)
        update["recent_job_loss"] = tracked
        update["business_closed"] = tracked
    return flags.model_copy(update=update) if update else flags


@router.post("/{session_id}/supplement")
def supplement(
    session_id: str,
    body: SupplementRequest,
    store: SessionStore = Depends(get_session_store),
) -> dict:
    state = get_session_or_404(session_id, store)
    income = _apply_supplement_income(state.income, body)
    household = _apply_supplement_household(state.household, body)
    extraction = _apply_supplement_debts(state.extraction or ExtractionResult(), body)
    flags = _apply_supplement_flags(state.flags, body)

    new_state = transition(state, SessionStage.S4_SUPPLEMENTED)
    new_state = new_state.model_copy(
        update={
            "income": income,
            "household": household,
            "extraction": extraction,
            "flags": flags,
            "updated_at": datetime.now(),
        }
    )
    store.save(new_state)
    return {"session_id": new_state.session_id, "stage": new_state.stage.value}


@router.post("/{session_id}/analyze")
def analyze_session(
    session_id: str,
    store: SessionStore = Depends(get_session_store),
    client: LLMClient = Depends(get_llm_client_dep),
) -> dict:
    state = get_session_or_404(session_id, store)
    analysis = run_analysis(state, client=client)

    new_state = transition(state, SessionStage.S5_ANALYZED)
    new_state = new_state.model_copy(update={"analysis": analysis, "updated_at": datetime.now()})
    store.save(new_state)
    return analysis.model_dump(mode="json")


@router.get("/{session_id}/result")
def get_result(session_id: str, store: SessionStore = Depends(get_session_store)) -> dict:
    state = get_session_or_404(session_id, store)
    if state.analysis is None:
        raise HTTPException(status_code=404, detail="아직 분석 결과가 없습니다.")
    return state.analysis.model_dump(mode="json")


@router.get("/{session_id}/explain")
def explain_session(session_id: str, store: SessionStore = Depends(get_session_store)) -> dict:
    """설명가능성 번들 (기획서 10.1 (4) 8개 항목)을 반환한다."""
    state = get_session_or_404(session_id, store)
    if state.analysis is None:
        raise HTTPException(status_code=404, detail="아직 분석 결과가 없습니다.")
    a = state.analysis
    return {
        "사용자_입력값": {
            "income": a.income.model_dump(mode="json"),
            "household": a.household.model_dump(mode="json"),
        },
        "AI_추출값": a.extraction.model_dump(mode="json"),
        "사용자_수정_이력": a.edit_history,
        "적용된_규칙과_버전": {
            "rule_version": a.rules.rule_version if a.rules else None,
            "dev_mode": a.dev_mode,
            "paths": [
                {
                    "path_id": p.path_id,
                    "policy_ref": (p.policy_ref.model_dump(mode="json") if p.policy_ref else None),
                }
                for p in (a.rules.paths if a.rules else ())
            ],
        },
        "계산_trace": [step.model_dump() for step in (a.cashflow.trace if a.cashflow else ())],
        "LLM_생성문": a.narrative.model_dump(mode="json") if a.narrative else None,
        "공식_근거와_기준일": {
            "policy_base_date": a.policy_base_date.isoformat() if a.policy_base_date else None,
        },
        "미확인_항목": [g.model_dump() for g in a.gaps.gaps],
    }


@router.post("/{session_id}/plan")
def create_plan(session_id: str, store: SessionStore = Depends(get_session_store)) -> dict:
    state = get_session_or_404(session_id, store)
    if state.analysis is None:
        raise HTTPException(status_code=404, detail="아직 분석 결과가 없습니다.")

    extraction = state.extraction or ExtractionResult()
    max_overdue_days = state.analysis.cashflow.max_overdue_days if state.analysis.cashflow else None
    plan = build_plan(
        max_overdue_days=max_overdue_days,
        income_proof_available=state.income.income_proof_available.value,
        debts_incomplete=not extraction.all_confirmed,
        income_drop_signal=has_income_drop_signal(state.flags),
    )

    new_analysis = state.analysis.model_copy(update={"plan": plan})
    new_state = transition(state, SessionStage.S6_PLANNED)
    new_state = new_state.model_copy(
        update={"analysis": new_analysis, "updated_at": datetime.now()}
    )
    store.save(new_state)
    return plan.model_dump()


@router.post("/{session_id}/report")
def create_report(
    session_id: str,
    options: ReportOptions | None = None,
    store: SessionStore = Depends(get_session_store),
) -> Response:
    state = get_session_or_404(session_id, store)
    if state.analysis is None:
        raise HTTPException(status_code=404, detail="아직 분석 결과가 없습니다.")

    pdf_bytes = render_summary(state.analysis, options or ReportOptions())

    new_state = transition(state, SessionStage.S7_REPORTED)
    new_state = new_state.model_copy(update={"updated_at": datetime.now()})
    store.save(new_state)
    return Response(content=pdf_bytes, media_type="application/pdf")
