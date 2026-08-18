"""
E5 — 근거 정확성 · 중대 환각 측정

전제:
  없음 (독립 실행 — 내장 테스트 배터리로 grounding.validate_grounding() 과
  narrative.generator.generate() 를 함께 검증한다)
출력:
  results/e5_grounding_check.csv
  reports/e5_grounding_check.md

측정 대상 2가지:
  1. 근거 정확성 — 그라운딩 검증기가 "실제로 근거 있는/없는" 문장을
     올바르게 분류하는 비율 (레이블링된 테스트 배터리 기준).
  2. 중대 환각 — narrative.generate() 가 최종적으로 반환하는 문장 중
     허용 집합 밖 숫자가 남아 있는 건수. 시스템이 그라운딩 실패 시
     템플릿으로 폴백하도록 설계되어 있으므로 항상 0이어야 한다(그 설계가
     실제로 지켜지는지 이 스크립트가 확인한다).
"""

from __future__ import annotations

import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dn.cashflow.calculator import compute  # noqa: E402
from dn.domain.enums import FieldSource, ProductType  # noqa: E402
from dn.domain.models import Debt, HouseholdProfile, IncomeProfile  # noqa: E402
from dn.domain.provenance import Tracked  # noqa: E402
from dn.llm.client import StubClient  # noqa: E402
from dn.narrative.generator import build_allowed_set, generate  # noqa: E402
from dn.narrative.grounding import validate_grounding  # noqa: E402

SEED = 42
_EVAL_CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"


def _known(value: Any) -> Tracked:
    return Tracked(value=value, source=FieldSource.DOCUMENT)


def _sample_context():
    debts = (
        Debt(
            debt_id="d0",
            creditor=_known("가나금융"),
            product_type=_known(ProductType.CREDIT_LOAN),
            balance=_known(Decimal("25000000")),
            overdue_days=_known(42),
            is_secured=_known(False),
            monthly_payment=_known(Decimal("1180000")),
        ),
    )
    income = IncomeProfile(monthly_net_income=_known(Decimal("2500000")))
    household = HouseholdProfile(essential_living_cost=_known(Decimal("1450000")))
    cashflow = compute(debts, income, household)
    return debts, cashflow


def _labeled_battery(cashflow) -> list[tuple[str, bool]]:
    """(문장, 실제로_그라운딩됨) 레이블 배터리. 표기 변형과 위반 사례를 섞는다."""
    shortfall = cashflow.monthly_shortfall
    return [
        (f"매달 {shortfall:,}원이 부족합니다.", True),
        ("매달 13만 원이 부족합니다.", True),
        ("매달 130,000원이 부족합니다.", True),
        (f"소득의 {cashflow.dti_ratio * 100}%가 상환에 들어갑니다.", True),
        ("연체일수는 42일입니다.", True),
        ("총 채무액은 4,600만원이 아니라 확인된 금액입니다.", False),  # 허용 집합 밖 억지 문장
        ("매달 9,999,999원이 부족합니다.", False),
        ("대출한도는 최대 5억원까지 가능합니다.", False),
        ("연체일수는 999일입니다.", False),
        ("신청하시면 반드시 승인됩니다.", True),  # 숫자 없음 → 그라운딩 관점에서는 위반 아님
    ]


def main() -> None:
    print("=== E5 근거 정확성 · 중대 환각 ===")
    np.random.default_rng(SEED)

    debts, cashflow = _sample_context()
    allowed = build_allowed_set(cashflow, debts, ())

    print("  [STAGE] 근거 정확성 배터리 검증")
    battery = _labeled_battery(cashflow)
    rows: list[dict[str, Any]] = []
    correct = 0
    for text, actually_grounded in battery:
        report = validate_grounding(text, allowed)
        predicted_grounded = report.grounded
        is_correct = predicted_grounded == actually_grounded
        correct += int(is_correct)
        rows.append(
            {
                "text": text,
                "actually_grounded": actually_grounded,
                "predicted_grounded": predicted_grounded,
                "correct": is_correct,
            }
        )
    evidence_accuracy = correct / len(battery)

    print("  [STAGE] 중대 환각 방어선 검증 (항상 환각을 만드는 스텁으로 generate() 호출)")
    hallucinating_client = StubClient(response="대출한도는 무조건 9,999,999,999원까지 승인됩니다.")
    narrative = generate(cashflow, (), debts, client=hallucinating_client)
    critical_hallucinations = 0
    for section in narrative.sections:
        report = validate_grounding(section.text, allowed)
        if not report.grounded:
            critical_hallucinations += 1
        rows.append(
            {
                "text": f"[generate() 최종 출력:{section.section.value}] {section.text}",
                "actually_grounded": True,
                "predicted_grounded": report.grounded,
                "correct": report.grounded,
            }
        )
        assert section.fallback_used, "환각 유도 스텁인데 fallback_used=False — 방어선 실패"

    df = pd.DataFrame(rows)
    eval_config = yaml.safe_load(_EVAL_CONFIG_PATH.read_text(encoding="utf-8"))
    root = Path(__file__).resolve().parents[1]
    results_dir = root / eval_config["paths"]["results"]
    reports_dir = root / eval_config["paths"]["reports"]
    results_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    csv_path = results_dir / "e5_grounding_check.csv"
    md_path = reports_dir / "e5_grounding_check.md"
    df.to_csv(csv_path, index=False)

    n = len(battery)
    measured_at = time.strftime("%Y-%m-%d")
    target_acc = eval_config["targets"]["e5_evidence_accuracy"]
    target_halluc = eval_config["targets"]["e5_critical_hallucination_max"]
    summary_lines = (
        f"근거 정확성 — 목표 {target_acc} 이상 / 실측 {evidence_accuracy:.4f} "
        f"(n={n}, {measured_at} 측정)\n"
        f"중대 환각 — 목표 {target_halluc}건 / 실측 {critical_hallucinations}건 "
        f"(n={len(narrative.sections)}, {measured_at} 측정)"
    )

    with md_path.open("w", encoding="utf-8") as f:
        f.write("# E5 — 근거 정확성 · 중대 환각\n\n")
        f.write(f"{summary_lines}\n\n")
        f.write(df.to_markdown(index=False, floatfmt=".4f"))
        f.write("\n")

    print(f"  근거 정확성: {evidence_accuracy:.4f}")
    print(f"  중대 환각: {critical_hallucinations}건")
    print(f"RESULT_PATHS: {csv_path}, {md_path}")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"[DONE] {time.time() - t0:.1f}s")
