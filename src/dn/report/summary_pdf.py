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
from dn.report.fonts import get_subset_font_path
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


def build_context(
    analysis: AnalysisResult, options: ReportOptions, *, settings: Settings | None = None
) -> dict[str, Any]:
    """PDF 생성의 1단계("preparing_data") — 세션 데이터를 템플릿 컨텍스트로 정리한다.

    LLM을 호출하지 않는다 — `s6_planned`에서 이미 확정된 `analysis`(cashflow·
    rules·narrative·plan)를 그대로 포맷팅만 한다.
    """
    settings = settings or get_settings()
    paths_ctx, questions = _paths_and_questions(analysis, options)
    font_path = get_subset_font_path(settings)
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
        # 로컬 서브셋 폰트가 준비됐으면 그 파일을 @font-face 로 직접 가리켜
        # WeasyPrint 가 매 렌더링마다 거대한 시스템 CJK 폰트를 서브셋하지
        # 않게 한다(fonts.py 참고, 실측 4.5초 → 0.4~0.5초). 못 만들었으면
        # (개발환경 등) None 이 되어 기존 시스템 폰트 이름 방식으로 폴백한다.
        "font_face_url": font_path.resolve().as_uri() if font_path else None,
    }


def render_html_from_context(context: dict[str, Any]) -> str:
    """PDF 생성의 2단계("rendering_html") — Jinja 템플릿을 HTML 문자열로 렌더링한다."""
    template = _env().get_template("summary.html")
    return template.render(**context)


def render_pdf_from_html(html: str) -> bytes:
    """PDF 생성의 3단계("rendering_pdf") — WeasyPrint 로 HTML을 PDF 바이트로 변환한다."""
    return weasyprint.HTML(string=html).write_pdf()


def render(
    analysis: AnalysisResult, options: ReportOptions, *, settings: Settings | None = None
) -> bytes:
    """`analysis` 를 상담용 요약서 PDF 바이트로 렌더링한다(3단계를 이어 호출하는 편의 함수)."""
    context = build_context(analysis, options, settings=settings)
    html = render_html_from_context(context)
    return render_pdf_from_html(html)
