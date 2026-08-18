"""상담용 요약서 PDF — 기획서 5.1 핵심 산출물(축소 불가).

1페이지를 넘기면 축약한다. 면책 문구는 항상 포함된다. 한글 렌더링은
시스템에 설치된 "Noto Sans CJK KR" 폰트에 의존한다(Debian/Ubuntu 계열은
`fonts-noto-cjk` 패키지로 설치). 별도 폰트 파일을 저장소에 번들하지 않는다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import weasyprint
from jinja2 import Environment, FileSystemLoader, select_autoescape

from dn.cashflow.formatting import format_ratio, format_won
from dn.domain.models import AnalysisResult, ReportOptions
from dn.settings import Settings, get_settings

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
_MAX_PATHS_SHOWN = 3
_MAX_QUESTIONS_SHOWN = 6
_DISCLAIMER = "제도 검토 결과는 자격 확정이 아니며 최종 자격은 공식 상담을 통해 확인해야 합니다."


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )


def _debt_rows(analysis: AnalysisResult, options: ReportOptions) -> list[dict[str, Any]]:
    rows = []
    for i, d in enumerate(analysis.extraction.debts):
        if options.include_creditor_names:
            creditor = d.creditor.value or "미확인"
        else:
            creditor = f"채무 {i + 1}"
        overdue = d.overdue_days.value if d.overdue_days.value is not None else "미확인"
        rows.append(
            {"creditor": creditor, "balance": format_won(d.balance.value), "overdue_days": overdue}
        )
    return rows


def _cashflow_context(analysis: AnalysisResult, options: ReportOptions) -> dict[str, Any] | None:
    cashflow = analysis.cashflow
    if cashflow is None:
        return None
    return {
        "total_debt": format_won(cashflow.total_debt),
        "monthly_total_payment": format_won(cashflow.monthly_total_payment),
        "monthly_available": format_won(cashflow.monthly_available),
        "monthly_shortfall": format_won(abs(cashflow.monthly_shortfall)),
        "shortfall_is_positive": cashflow.monthly_shortfall >= 0,
        "dti_ratio": (format_ratio(cashflow.dti_ratio) if options.include_income else "비공개"),
    }


def _paths_and_questions(
    analysis: AnalysisResult, options: ReportOptions
) -> tuple[list[dict[str, Any]], list[str]]:
    if not options.include_paths or analysis.rules is None:
        return [], []
    paths_ctx = []
    questions: list[str] = []
    for p in analysis.rules.paths[:_MAX_PATHS_SHOWN]:
        paths_ctx.append({"name": p.name, "agency": p.agency, "status": p.status.value})
        questions.extend(p.consult_questions)
    if not options.include_questions:
        questions = []
    return paths_ctx, questions[:_MAX_QUESTIONS_SHOWN]


def _build_context(
    analysis: AnalysisResult, options: ReportOptions, *, settings: Settings
) -> dict[str, Any]:
    paths_ctx, questions = _paths_and_questions(analysis, options)
    return {
        "service_name": settings.config.meta.service_name,
        "debts": _debt_rows(analysis, options),
        "cashflow": _cashflow_context(analysis, options),
        "unknowns": [g.label for g in analysis.gaps.gaps],
        "paths": paths_ctx,
        "questions": questions,
        "policy_base_date": analysis.policy_base_date,
        "disclaimer": _DISCLAIMER,
        "options": options,
        "font_family": settings.config.report.font_family,
    }


def render(
    analysis: AnalysisResult, options: ReportOptions, *, settings: Settings | None = None
) -> bytes:
    """`analysis` 를 상담용 요약서 PDF 바이트로 렌더링한다."""
    settings = settings or get_settings()
    template = _env().get_template("summary.html")
    html = template.render(**_build_context(analysis, options, settings=settings))
    return weasyprint.HTML(string=html).write_pdf()
