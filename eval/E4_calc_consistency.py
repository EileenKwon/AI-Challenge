"""
E4 — 계산 일관성 측정

전제:
  tests/golden/*.yaml (T08 골든 케이스)
출력:
  results/e4_calc_consistency.csv
  reports/e4_calc_consistency.md
"""

from __future__ import annotations

import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dn.cashflow.calculator import compute  # noqa: E402
from dn.domain.enums import FieldSource, ProductType  # noqa: E402
from dn.domain.models import Debt, HouseholdProfile, IncomeProfile  # noqa: E402
from dn.domain.provenance import Tracked  # noqa: E402

_EVAL_CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"


def _tracked(value: Any) -> Tracked:
    if value is None:
        return Tracked()
    return Tracked(value=value, source=FieldSource.DOCUMENT)


def _money(raw: dict[str, Any], key: str) -> Decimal | None:
    return Decimal(str(raw[key])) if key in raw else None


def _debt_from_yaml(raw: dict[str, Any], index: int) -> Debt:
    product_type = ProductType(raw["product_type"]) if raw.get("product_type") else None
    return Debt(
        debt_id=f"d{index}",
        creditor=_tracked(raw.get("creditor")),
        product_type=_tracked(product_type),
        balance=_tracked(_money(raw, "balance")),
        overdue_days=_tracked(raw.get("overdue_days")),
        is_secured=_tracked(raw.get("is_secured")),
        monthly_payment=_tracked(_money(raw, "monthly_payment")),
    )


def _income_from_yaml(raw: dict[str, Any]) -> IncomeProfile:
    return IncomeProfile(
        monthly_net_income=_tracked(_money(raw, "monthly_net_income")),
        support_income=_tracked(_money(raw, "support_income")),
    )


def _household_from_yaml(raw: dict[str, Any]) -> HouseholdProfile:
    return HouseholdProfile(
        essential_living_cost=_tracked(_money(raw, "essential_living_cost")),
        housing_cost=_tracked(_money(raw, "housing_cost")),
        medical_care_cost=_tracked(_money(raw, "medical_care_cost")),
        other_fixed_cost=_tracked(_money(raw, "other_fixed_cost")),
        dependents=_tracked(raw.get("dependents")),
    )


def main() -> None:
    print("=== E4 계산 일관성 ===")
    eval_config = yaml.safe_load(_EVAL_CONFIG_PATH.read_text(encoding="utf-8"))
    golden_dir = Path(__file__).resolve().parents[1] / eval_config["paths"]["golden"]
    if not golden_dir.exists():
        print(f"[ERR] 골든 케이스 디렉토리가 없습니다: {golden_dir}")
        sys.exit(1)

    golden_files = sorted(p for p in golden_dir.glob("*.yaml"))
    if not golden_files:
        print(f"[ERR] 골든 케이스 파일이 없습니다: {golden_dir}")
        sys.exit(1)

    print(f"  [STAGE] {len(golden_files)}개 골든 케이스 로딩")
    rows: list[dict[str, Any]] = []
    for path in golden_files:
        case = yaml.safe_load(path.read_text(encoding="utf-8"))
        if "expected" not in case:
            continue
        debts = tuple(_debt_from_yaml(d, i) for i, d in enumerate(case["input"]["debts"]))
        income = _income_from_yaml(case["input"].get("income") or {})
        household = _household_from_yaml(case["input"].get("household") or {})
        result = compute(debts, income, household)
        expected = case["expected"]

        fields = ["total_debt", "monthly_total_payment", "monthly_available", "monthly_shortfall"]
        max_error = Decimal("0")
        for field in fields:
            actual = getattr(result, field)
            exp = Decimal(str(expected[field]))
            max_error = max(max_error, abs(actual - exp))

        rows.append(
            {
                "case_id": case["id"],
                "max_abs_error_won": int(max_error),
                "pass": max_error == 0,
            }
        )

    df = pd.DataFrame(rows)
    results_dir = Path(__file__).resolve().parents[1] / eval_config["paths"]["results"]
    reports_dir = Path(__file__).resolve().parents[1] / eval_config["paths"]["reports"]
    results_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    csv_path = results_dir / "e4_calc_consistency.csv"
    md_path = reports_dir / "e4_calc_consistency.md"
    df.to_csv(csv_path, index=False)

    n = len(df)
    measured_at = time.strftime("%Y-%m-%d")
    max_error = df["max_abs_error_won"].max() if n else "N/A"
    summary_line = (
        f"계산 일관성 — 목표 오차 0 / 실측 최대오차 {max_error}원 (n={n}, {measured_at} 측정)"
    )
    with md_path.open("w", encoding="utf-8") as f:
        f.write("# E4 — 계산 일관성\n\n")
        f.write(f"{summary_line}\n\n")
        f.write(df.to_markdown(index=False, floatfmt=".4f"))
        f.write("\n")

    print(f"  통과: {int(df['pass'].sum())}/{n}")
    print(f"RESULT_PATHS: {csv_path}, {md_path}")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"[DONE] {time.time() - t0:.1f}s")
