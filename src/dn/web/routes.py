"""화면 7종 페이지 라우터. 세션 상태를 읽어 템플릿에 넘기기만 한다(로직 없음)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from dn.api.deps import get_session_or_404, get_session_store
from dn.cashflow.formatting import format_ratio, format_won
from dn.domain.models import ExtractionResult, SessionState
from dn.reconcile.questions import (
    has_income_drop_signal,
    has_overdue,
    has_secured_debt,
    load_conditional_questions,
    load_fixed_questions,
    select_active_questions,
)
from dn.settings import get_settings
from dn.storage.session_store import SessionStore

router = APIRouter(prefix="/web/session", tags=["web"])

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

_STAGE_STEP = {
    "s0_consent": 0,
    "s1_uploaded": 1,
    "s2_extracted": 2,
    "s3_confirmed": 3,
    "s4_supplemented": 4,
    "s5_analyzed": 5,
    "s6_planned": 6,
    "s7_reported": 7,
}

_TIMING_LABEL = {
    "today": "오늘",
    "d1": "1일 이내",
    "d2": "2일 이내",
    "before_consult": "상담 전",
    "after_consult": "상담 후",
}

_STATUS_LABEL = {
    "candidate": "우선 검토 가능",
    "needs_info": "추가 확인 필요",
    "excluded": "제외",
    "undetermined": "판정 불가",
}


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=select_autoescape(["html"])
    )


def _base_context(state: SessionState) -> dict[str, Any]:
    settings = get_settings()
    return {
        "session_id": state.session_id,
        "service_name": settings.config.meta.service_name,
        "policy_base_date": settings.config.meta.policy_base_date,
        "current_step": _STAGE_STEP.get(state.stage.value, 0),
        "dev_mode": settings.config.rules.allow_unverified_cards,
    }


def _debt_view(debt) -> dict[str, Any]:
    balance = debt.balance
    low_confidence = balance.confidence is not None and balance.confidence < Decimal("0.7")
    return {
        "creditor": debt.creditor.value or "미확인",
        "creditor_source": debt.creditor.source.value,
        "product_type": (debt.product_type.value.value if debt.product_type.value else "미확인"),
        "product_type_source": debt.product_type.source.value,
        "balance": format_won(balance.value),
        "balance_source": balance.source.value,
        "overdue_days": (
            debt.overdue_days.value if debt.overdue_days.value is not None else "미확인"
        ),
        "overdue_days_source": debt.overdue_days.source.value,
        "low_confidence": low_confidence,
    }


def render_page(template_name: str, context: dict[str, Any]) -> HTMLResponse:
    template = _env().get_template(template_name)
    return HTMLResponse(template.render(**context))


@router.get("/{session_id}/intro", response_class=HTMLResponse)
def intro_page(session_id: str, store: SessionStore = Depends(get_session_store)) -> HTMLResponse:
    state = get_session_or_404(session_id, store)
    return render_page("01_intro.html", _base_context(state))


@router.get("/{session_id}/upload", response_class=HTMLResponse)
def upload_page(session_id: str, store: SessionStore = Depends(get_session_store)) -> HTMLResponse:
    state = get_session_or_404(session_id, store)
    ctx = _base_context(state)
    ctx["synthetic_cases"] = []
    return render_page("02_upload.html", ctx)


@router.get("/{session_id}/extraction", response_class=HTMLResponse)
def extraction_page(
    session_id: str, store: SessionStore = Depends(get_session_store)
) -> HTMLResponse:
    state = get_session_or_404(session_id, store)
    extraction = state.extraction or ExtractionResult()
    ctx = _base_context(state)
    ctx["debts"] = [_debt_view(d) for d in extraction.debts]
    return render_page("03_extraction.html", ctx)


@router.get("/{session_id}/supplement", response_class=HTMLResponse)
def supplement_page(
    session_id: str, store: SessionStore = Depends(get_session_store)
) -> HTMLResponse:
    state = get_session_or_404(session_id, store)
    extraction = state.extraction or ExtractionResult()
    ctx = _base_context(state)
    ctx["debts"] = [_debt_view(d) for d in extraction.debts]
    ctx["fixed_questions"] = load_fixed_questions()
    active = select_active_questions(
        secured_debt_present=has_secured_debt(extraction.debts),
        overdue_present=has_overdue(extraction.debts),
        income_drop_present=has_income_drop_signal(state.flags),
    )
    conditional_ids = {q.qid for q in load_conditional_questions()}
    ctx["conditional_questions"] = [q for q in active if q.qid in conditional_ids]
    return render_page("04_supplement.html", ctx)


@router.get("/{session_id}/result", response_class=HTMLResponse)
def result_page(session_id: str, store: SessionStore = Depends(get_session_store)) -> HTMLResponse:
    state = get_session_or_404(session_id, store)
    ctx = _base_context(state)
    analysis = state.analysis
    cashflow = analysis.cashflow if analysis else None

    if cashflow is not None:
        total_ref = max(cashflow.monthly_available, cashflow.monthly_total_payment, Decimal(1))
        ctx["cashflow"] = {
            "total_debt": format_won(cashflow.total_debt),
            "monthly_available": format_won(cashflow.monthly_available),
            "monthly_total_payment": format_won(cashflow.monthly_total_payment),
            "monthly_shortfall": format_won(abs(cashflow.monthly_shortfall)),
            "shortfall_is_positive": cashflow.monthly_shortfall >= 0,
            "dti_ratio": format_ratio(cashflow.dti_ratio),
        }
        ctx["available_ratio"] = int(min(cashflow.monthly_available, total_ref) / total_ref * 100)
        ctx["payment_ratio"] = int(min(cashflow.monthly_total_payment, total_ref) / total_ref * 100)
        ctx["trace"] = list(cashflow.trace)
        extraction = state.extraction or ExtractionResult()
        known = [d for d in extraction.debts if d.balance.value and d.creditor.value]
        total = sum((d.balance.value for d in known), Decimal(0)) or Decimal(1)
        ctx["creditor_shares"] = [
            {"creditor": d.creditor.value, "percent": int(d.balance.value / total * 100)}
            for d in known
        ]
    else:
        ctx["cashflow"] = None
        ctx["available_ratio"] = 0
        ctx["payment_ratio"] = 0
        ctx["trace"] = []
        ctx["creditor_shares"] = []

    ctx["unknowns"] = [g.label for g in analysis.gaps.gaps] if analysis else []
    ctx["narrative_cashflow_text"] = None
    if analysis and analysis.narrative:
        for section in analysis.narrative.sections:
            if section.section.value == "cashflow":
                ctx["narrative_cashflow_text"] = section.text
    return render_page("05_result.html", ctx)


@router.get("/{session_id}/paths", response_class=HTMLResponse)
def paths_page(session_id: str, store: SessionStore = Depends(get_session_store)) -> HTMLResponse:
    state = get_session_or_404(session_id, store)
    ctx = _base_context(state)
    rules = state.analysis.rules if state.analysis else None
    ctx["paths"] = [
        {
            "name": p.name,
            "agency": p.agency,
            "priority": p.priority,
            "status_label": _STATUS_LABEL.get(p.status.value, p.status.value),
            "met": p.met,
            "unknown": p.unknown,
            "swing_factors": p.swing_factors,
            "user_evidence": p.user_evidence,
            "policy_ref": p.policy_ref,
            "next_actions": p.next_actions,
            "consult_questions": p.consult_questions,
            "why_final_check": p.why_final_check,
        }
        for p in (rules.paths if rules else ())
    ]
    ctx["excluded_paths"] = list(rules.excluded_paths) if rules else []
    return render_page("06_paths.html", ctx)


@router.get("/{session_id}/plan", response_class=HTMLResponse)
def plan_page(session_id: str, store: SessionStore = Depends(get_session_store)) -> HTMLResponse:
    state = get_session_or_404(session_id, store)
    ctx = _base_context(state)
    plan = state.analysis.plan if state.analysis else None
    ctx["plan_items"] = [
        {
            "timing_label": _TIMING_LABEL.get(item.timing.value, item.timing.value),
            "text": item.text,
            "related_agency": item.related_agency,
        }
        for item in (plan.items if plan else ())
    ]
    return render_page("07_plan.html", ctx)
