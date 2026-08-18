"""분석 파이프라인 오케스트레이터 — ARCHITECTURE.md §8의 9단계.

```
1. state >= S4 확인                        ← 실패 시 StateTransitionError
2. cashflow.compute()                      ← 항상 실행, 항상 반환
3. triage.evaluate()  REFER→규칙 엔진 생략 / PROCEED→4번으로
4. policy_card.load(verified_only=True)    카드 0개 → undetermined=True
5. rules.evaluate() → PathCandidate[]
6. 상위 3개 선별 (rules.evaluate() 내부에서 처리)
7. narrative.generate(cashflow, paths)     ← LLM
8. safety.output_filter + grounding        실패 → 템플릿 fallback
9. AnalysisResult 조립 (설명가능성 번들 포함)
```

`rules` 단계의 예외가 `cashflow` 결과를 삼키지 않는다. `PolicyCardError` 는
`undetermined=True` 로 강등되고 현금흐름은 그대로 반환된다.
"""

from __future__ import annotations

from datetime import date, datetime

from dn.cashflow.calculator import compute as compute_cashflow
from dn.domain.enums import SectionKind, SessionStage, TriageDecision
from dn.domain.errors import PolicyCardError
from dn.domain.models import (
    AnalysisResult,
    ExtractionResult,
    Narrative,
    NarrativeSection,
    RuleEngineResult,
    SessionState,
)
from dn.llm.client import LLMClient
from dn.narrative import templates as narrative_templates
from dn.narrative.generator import generate as generate_narrative
from dn.pipeline.stages import assert_at_least
from dn.reconcile.conflict_detector import detect_conflicts
from dn.reconcile.gap_detector import detect_gaps
from dn.rules.engine import evaluate as evaluate_rules
from dn.rules.facts import build_facts
from dn.rules.policy_card import load_usable_cards
from dn.rules.triage import evaluate as evaluate_triage
from dn.safety.output_filter import check as check_output
from dn.settings import Settings, get_settings


def _load_rules_result(
    facts: dict, *, has_unresolved_conflicts: bool, settings: Settings
) -> RuleEngineResult:
    """4~6단계. `PolicyCardError` 는 삼키지 않고 undetermined 로 강등한다."""
    try:
        cards, dev_mode = load_usable_cards(settings=settings)
    except PolicyCardError as exc:
        return RuleEngineResult(
            undetermined=True,
            undetermined_reasons=(f"정책 카드를 불러올 수 없습니다: {exc}",),
        )
    return evaluate_rules(
        facts, cards, dev_mode=dev_mode, has_unresolved_conflicts=has_unresolved_conflicts
    )


def _filtered_section(section: NarrativeSection, *, cashflow, paths) -> NarrativeSection:
    """8단계. 출력 필터를 통과하지 못하면 결정론적 템플릿으로 대체한다."""
    result = check_output(section.text, section.section)
    if result.passed:
        return section
    if section.section == SectionKind.CASHFLOW:
        return narrative_templates.cashflow_fallback(cashflow)
    return narrative_templates.path_fallback(paths)


def analyze(
    state: SessionState,
    *,
    client: LLMClient | None = None,
    now: datetime | None = None,
    settings: Settings | None = None,
) -> AnalysisResult:
    """9단계 분석 파이프라인을 실행한다. `cashflow` 는 항상 계산·반환된다."""
    settings = settings or get_settings()
    assert_at_least(state, SessionStage.S4_SUPPLEMENTED)  # 1

    extraction = state.extraction or ExtractionResult()
    debts = extraction.debts

    cashflow = compute_cashflow(debts, state.income, state.household)  # 2

    gaps = detect_gaps(debts, state.income)
    conflicts = detect_conflicts(extraction, state.household, settings=settings)
    facts = build_facts(debts, state.income, cashflow, state.flags)

    extraction_quality = {
        "has_unresolved_conflicts": conflicts.has_unresolved,
        "low_confidence": bool(extraction.low_confidence_fields),
    }
    triage_result = evaluate_triage(facts, extraction_quality)  # 3

    rules_result: RuleEngineResult | None = None
    if triage_result.decision == TriageDecision.PROCEED:
        rules_result = _load_rules_result(  # 4~6
            facts, has_unresolved_conflicts=conflicts.has_unresolved, settings=settings
        )

    paths = rules_result.paths if rules_result is not None else ()
    narrative_raw = generate_narrative(cashflow, paths, debts, client=client)  # 7

    if triage_result.decision == TriageDecision.REFER:
        # 규칙 엔진만 생략한다 — 현금흐름 섹션은 그대로 남긴다.
        sections = tuple(s for s in narrative_raw.sections if s.section == SectionKind.CASHFLOW)
    else:
        sections = narrative_raw.sections
    narrative = Narrative(
        sections=tuple(_filtered_section(s, cashflow=cashflow, paths=paths) for s in sections)  # 8
    )

    policy_base_date: date | None = None
    if rules_result is not None and rules_result.policy_base_date is not None:
        policy_base_date = rules_result.policy_base_date
    else:
        policy_base_date = date.fromisoformat(settings.config.meta.policy_base_date)

    return AnalysisResult(  # 9
        session_id=state.session_id,
        analyzed_at=now or datetime.now(),
        extraction=extraction,
        income=state.income,
        household=state.household,
        flags=state.flags,
        cashflow=cashflow,
        triage=triage_result,
        rules=rules_result,
        narrative=narrative,
        gaps=gaps,
        conflicts=conflicts,
        policy_base_date=policy_base_date,
        dev_mode=rules_result.dev_mode if rules_result is not None else False,
    )
