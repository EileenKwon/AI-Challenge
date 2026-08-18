"""T17 — 상담용 요약서 PDF 테스트. 기획서 15장 김하늘 사례로 검증한다."""

from __future__ import annotations

import io
from datetime import date, datetime
from decimal import Decimal

import pypdf
import pytest

from dn.domain.enums import FieldSource, PathStatus, ProductType
from dn.domain.models import (
    AnalysisResult,
    CashflowResult,
    Debt,
    ExtractionResult,
    Gap,
    GapReport,
    HouseholdProfile,
    IncomeProfile,
    PathCandidate,
    PolicyRef,
    ReportOptions,
    RuleEngineResult,
    SituationFlags,
)
from dn.domain.provenance import Tracked
from dn.report.summary_pdf import render


def _known(value):
    return Tracked(value=value, source=FieldSource.DOCUMENT)


def _kimhaneul_analysis() -> AnalysisResult:
    debts = (
        Debt(
            debt_id="d0",
            creditor=_known("A금융"),
            product_type=_known(ProductType.CREDIT_LOAN),
            balance=_known(Decimal("25000000")),
            overdue_days=_known(42),
            is_secured=_known(False),
        ),
        Debt(
            debt_id="d1",
            creditor=_known("B카드"),
            product_type=_known(ProductType.CARD_LOAN),
            balance=_known(Decimal("14000000")),
            overdue_days=_known(0),
            is_secured=_known(False),
        ),
        Debt(
            debt_id="d2",
            creditor=_known("C캐피탈"),
            product_type=_known(ProductType.CREDIT_LOAN),
            balance=_known(Decimal("7000000")),
            overdue_days=_known(0),
            is_secured=_known(False),
        ),
    )
    cashflow = CashflowResult(
        total_debt=Decimal("46000000"),
        monthly_total_payment=Decimal("1180000"),
        monthly_available=Decimal("1050000"),
        monthly_shortfall=Decimal("130000"),
        dti_ratio=Decimal("0.472"),
        max_overdue_days=42,
    )
    gaps = GapReport(
        gaps=(
            Gap(rule_id="GAP_RATE", label="금리 미확인", target="debt_0.interest_rate", impact="-"),
            Gap(
                rule_id="GAP_INCOME_PROOF",
                label="소득증빙 가능 여부 미확인",
                target="income.income_proof_available",
                impact="-",
            ),
        )
    )
    paths = (
        PathCandidate(
            path_id="pre_debt_adjustment",
            name="사전채무조정",
            priority=2,
            agency="신용회복위원회",
            status=PathStatus.NEEDS_INFO,
            consult_questions=("예상 납입기간은 어느 정도인가",),
            policy_ref=PolicyRef(
                card_id="pre_debt_adjustment",
                card_version="2026-08-13.1",
                title="사전채무조정",
                policy_base_date=date(2026, 8, 13),
                verified=False,
            ),
        ),
    )
    rules = RuleEngineResult(paths=paths, policy_base_date=date(2026, 8, 13))

    return AnalysisResult(
        session_id="s1",
        analyzed_at=datetime(2026, 8, 18),
        extraction=ExtractionResult(debts=debts),
        income=IncomeProfile(monthly_net_income=_known(Decimal("2500000"))),
        household=HouseholdProfile(essential_living_cost=_known(Decimal("1450000"))),
        flags=SituationFlags(),
        cashflow=cashflow,
        rules=rules,
        gaps=gaps,
        policy_base_date=date(2026, 8, 13),
    )


def _pages(pdf_bytes: bytes) -> pypdf.PdfReader:
    return pypdf.PdfReader(io.BytesIO(pdf_bytes))


def test_pdf_generation_succeeds_for_kimhaneul_case() -> None:
    pdf_bytes = render(_kimhaneul_analysis(), ReportOptions())
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1000


def test_pdf_is_exactly_one_page() -> None:
    pdf_bytes = render(_kimhaneul_analysis(), ReportOptions())
    reader = _pages(pdf_bytes)
    assert len(reader.pages) == 1


def test_korean_text_is_extractable() -> None:
    pdf_bytes = render(_kimhaneul_analysis(), ReportOptions())
    reader = _pages(pdf_bytes)
    text = reader.pages[0].extract_text()
    assert "상담용 요약서" in text
    assert "채무 현황" in text
    assert "A금융" in text


def test_disclaimer_is_always_present() -> None:
    pdf_bytes = render(_kimhaneul_analysis(), ReportOptions())
    text = _pages(pdf_bytes).pages[0].extract_text()
    assert "자격 확정이 아니며" in text


def test_confirmed_numbers_appear_in_pdf() -> None:
    pdf_bytes = render(_kimhaneul_analysis(), ReportOptions())
    text = _pages(pdf_bytes).pages[0].extract_text()
    assert "13만 원" in text


# --- include_creditor_names=False ------------------------------------------------


def test_creditor_names_excluded_when_option_disabled() -> None:
    options = ReportOptions(include_creditor_names=False)
    pdf_bytes = render(_kimhaneul_analysis(), options)
    text = _pages(pdf_bytes).pages[0].extract_text()
    assert "A금융" not in text
    assert "B카드" not in text
    assert "C캐피탈" not in text
    assert "채무 1" in text


def test_creditor_names_included_by_default() -> None:
    pdf_bytes = render(_kimhaneul_analysis(), ReportOptions())
    text = _pages(pdf_bytes).pages[0].extract_text()
    assert "A금융" in text


# --- 기타 옵션 ---------------------------------------------------------------------


def test_include_paths_false_hides_path_section() -> None:
    options = ReportOptions(include_paths=False)
    pdf_bytes = render(_kimhaneul_analysis(), options)
    text = _pages(pdf_bytes).pages[0].extract_text()
    assert "사전채무조정" not in text


def test_include_questions_false_hides_questions() -> None:
    options = ReportOptions(include_questions=False)
    pdf_bytes = render(_kimhaneul_analysis(), options)
    text = _pages(pdf_bytes).pages[0].extract_text()
    assert "예상 납입기간은 어느 정도인가" not in text


@pytest.mark.parametrize(
    "options",
    [
        ReportOptions(),
        ReportOptions(include_creditor_names=False),
        ReportOptions(include_paths=False),
        ReportOptions(include_questions=False),
        ReportOptions(include_income=False),
    ],
)
def test_all_option_combinations_stay_one_page(options: ReportOptions) -> None:
    pdf_bytes = render(_kimhaneul_analysis(), options)
    assert len(_pages(pdf_bytes).pages) == 1
