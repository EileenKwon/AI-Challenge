"""
report_builder — 제출용 지표표 생성 (기획서 14.3 10개 지표)

전제:
  reports/e1_extraction_f1.md ~ reports/e6_safety_redteam.md
  (E1~E6_*.py 를 먼저 실행해야 한다)
출력:
  reports/metrics_summary.md

측정 원칙(기획서 14.3): 실제 측정값과 표본 수(n)를 반드시 병기한다.
목표치만 적힌 표는 검증되지 않은 주장으로 간주한다.

"사용자 이해도"와 "준비시간"은 실제 사용자 대상 설문·타이밍 스터디가
필요한 지표라 이 스크립트(자동화 코드)로는 측정할 수 없다. 목표치만 적고
"미측정"으로 정직하게 표기한다 — 숫자를 지어내지 않는다.
"""

from __future__ import annotations

import json
import re
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dn.cashflow.calculator import compute  # noqa: E402
from dn.domain.enums import FieldSource, ProductType  # noqa: E402
from dn.domain.models import Debt, HouseholdProfile, IncomeProfile  # noqa: E402
from dn.domain.provenance import Tracked  # noqa: E402

SEED = 42
_EVAL_CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"
_SUMMARY_LINE_RE = re.compile(r".+—.+목표.+실측.+측정\)")


def _summary_lines_from(md_path: Path) -> list[str]:
    if not md_path.exists():
        return []
    lines = md_path.read_text(encoding="utf-8").splitlines()
    return [line for line in lines if _SUMMARY_LINE_RE.match(line)]


def _known(value: Any) -> Tracked:
    return Tracked(value=value, source=FieldSource.DOCUMENT)


def _debt_from_label(raw: dict[str, Any]) -> Debt:
    product_type = ProductType(raw["product_type"]) if raw.get("product_type") else None
    balance = Decimal(str(raw["balance"])) if raw.get("balance") is not None else None
    overdue_days = raw.get("overdue_days")
    is_secured = raw.get("is_secured")
    return Debt(
        debt_id="d",
        creditor=_known(raw.get("creditor")),
        product_type=_known(product_type) if product_type else Tracked(),
        balance=_known(balance) if balance is not None else Tracked(),
        overdue_days=_known(overdue_days) if overdue_days is not None else Tracked(),
        is_secured=_known(is_secured) if is_secured is not None else Tracked(),
        monthly_payment=Tracked(),  # 신용정보조회서에는 없는 항목 — 라벨에도 없음
    )


def _measure_input_completeness(root: Path, eval_config: dict) -> tuple[float, int]:
    """합성 라벨을 확정 입력이라 가정했을 때의 핵심 필드 확보율 평균."""
    label_dir = root / eval_config["paths"]["synthetic_labels"]
    if not label_dir.exists():
        return 0.0, 0

    scores = []
    for label_path in sorted(label_dir.glob("*.json")):
        label = json.loads(label_path.read_text(encoding="utf-8"))
        debts = tuple(_debt_from_label(d) for d in label["debts"])
        income = IncomeProfile(monthly_net_income=_known(Decimal("2000000")))
        household = HouseholdProfile(essential_living_cost=_known(Decimal("1000000")))
        result = compute(debts, income, household)
        scores.append(float(result.completeness))
    return (float(np.mean(scores)) if scores else 0.0), len(scores)


def main() -> None:
    print("=== 평가 지표 요약 리포트 생성 ===")
    eval_config = yaml.safe_load(_EVAL_CONFIG_PATH.read_text(encoding="utf-8"))
    root = Path(__file__).resolve().parents[1]
    reports_dir = root / eval_config["paths"]["reports"]

    e_scripts = {
        "E1": "e1_extraction_f1.md",
        "E2": "e2_number_accuracy.md",
        "E3": "e3_path_recall.md",
        "E4": "e4_calc_consistency.md",
        "E5": "e5_grounding_check.md",
        "E6": "e6_safety_redteam.md",
    }

    missing = [name for name, fname in e_scripts.items() if not (reports_dir / fname).exists()]
    if missing:
        print(f"[ERR] 먼저 실행해야 하는 평가 스크립트가 있습니다: {missing}")
        sys.exit(1)

    print("  [STAGE] E1~E6 요약 문구 수집")
    collected: list[str] = []
    for name, fname in e_scripts.items():
        lines = _summary_lines_from(reports_dir / fname)
        collected.extend(lines)
        print(f"    {name}: {len(lines)}개 지표 문구")

    print("  [STAGE] 입력 완성도 측정 (합성 라벨 기반)")
    completeness, n_completeness = _measure_input_completeness(root, eval_config)
    measured_at = time.strftime("%Y-%m-%d")
    target_completeness = eval_config["targets"]["input_completeness"]
    collected.append(
        f"입력 완성도 — 목표 {target_completeness} 이상 / 실측 {completeness:.4f} "
        f"(n={n_completeness}, {measured_at} 측정)"
    )

    unmeasured = [
        "사용자 이해도 — 목표 평균 4점 이상(5점 척도, n=5) / 실측 미측정 "
        "(실제 사용자 설문이 필요한 지표. 자동화 스크립트로 측정 불가)",
        "준비시간 — 목표 수동 정리 대비 30% 이상 단축(n=5) / 실측 미측정 "
        "(실제 사용자 타이밍 스터디가 필요한 지표. 자동화 스크립트로 측정 불가)",
    ]

    md_path = reports_dir / "metrics_summary.md"
    with md_path.open("w", encoding="utf-8") as f:
        # 지표 개수는 세어서 쓴다. 기획서 기준 10개에서 출발했지만 E6 에
        # 연체일수 경계 항목이 추가되며 늘었고, 숫자를 손으로 적어 두면
        # 제출 문서의 머리글과 실제 목록이 어긋난다(실제로 어긋났다).
        total = len(collected) + len(unmeasured)
        f.write(f"# 평가 지표 요약 (기획서 14.3 기준 10개 + 이후 추가분, 총 {total}개)\n\n")
        f.write(f"측정일: {measured_at}\n\n")
        f.write(
            "측정 원칙: 실제 측정값과 표본 수(n)를 병기한다. "
            "목표치만 적힌 지표는 검증되지 않은 주장으로 간주한다.\n\n"
        )
        f.write(f"## 자동 측정 지표 ({len(collected)}개)\n\n")
        for line in collected:
            f.write(f"- {line}\n")
        f.write(f"\n## 사용자 스터디 필요 지표 ({len(unmeasured)}개, 자동화 불가)\n\n")
        for line in unmeasured:
            f.write(f"- {line}\n")
        f.write("\n")

        stub_flag = any("STUB_MODE" in line for line in collected)
        if stub_flag:
            f.write(
                "> **주의**: E1/E2 는 이 실행 환경에 `ANTHROPIC_API_KEY` 가 설정되어 있지 않아 "
                "`StubClient`(빈 응답)로 실행되었다. 해당 두 지표는 실제 LLM 추출 성능을 "
                "반영하지 않는다 — API 키가 설정된 환경에서 재실행해야 유효한 값이 나온다.\n"
            )

    print(f"  총 {len(collected)}개 자동 측정 지표 + {len(unmeasured)}개 미측정 지표 기록")
    print(f"RESULT_PATHS: {md_path}")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"[DONE] {time.time() - t0:.1f}s")
