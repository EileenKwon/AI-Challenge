"""T15 — 출력 안전 필터 테스트.

확정 표현이 제도 섹션(PATH/PLAN)에서는 차단되고 현금흐름 섹션에서는
통과하는지 확인한다.
"""

from __future__ import annotations

from dn.domain.enums import SectionKind
from dn.safety.output_filter import check

# --- confirmatory: 섹션별로 다르게 적용 ------------------------------------------


def test_confirmatory_phrase_blocked_in_path_section() -> None:
    result = check("신청이 가능합니다.", SectionKind.PATH)
    assert result.passed is False
    assert "confirmatory" in result.matched_categories


def test_confirmatory_phrase_blocked_in_plan_section() -> None:
    result = check("가장 유리한 선택입니다.", SectionKind.PLAN)
    assert result.passed is False


def test_cashflow_section_allows_definite_shortfall_statement() -> None:
    result = check("매달 13만 원이 부족합니다.", SectionKind.CASHFLOW)
    assert result.passed is True
    assert result.matched_categories == ()


def test_confirmatory_phrase_would_be_flagged_in_cashflow_if_present() -> None:
    # confirmatory 는 cashflow 섹션에는 적용되지 않으므로 이 문장도 통과해야 한다.
    result = check("신청이 가능합니다.", SectionKind.CASHFLOW)
    assert result.passed is True


def test_report_section_not_covered_by_confirmatory() -> None:
    result = check("신청이 가능합니다.", SectionKind.REPORT)
    assert result.passed is True


# --- stigmatizing / risky_advice: 전 섹션 적용 -----------------------------------


def test_stigmatizing_phrase_blocked_everywhere() -> None:
    for section in SectionKind:
        result = check("신용불량자가 되지 않으려면...", section)
        assert result.passed is False, section


def test_risky_advice_blocked_everywhere() -> None:
    for section in SectionKind:
        result = check("일부러 연체하는 것을 고려해보세요.", section)
        assert result.passed is False, section


def test_clean_text_passes_in_every_section() -> None:
    for section in SectionKind:
        result = check("현재 확인된 정보를 안내해 드립니다.", section)
        assert result.passed is True, section


def test_section_argument_is_required() -> None:
    import inspect

    sig = inspect.signature(check)
    assert "section" in sig.parameters
    assert sig.parameters["section"].default is inspect.Parameter.empty
