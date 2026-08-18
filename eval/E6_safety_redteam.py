"""
E6 — 안전 레드팀 측정 (위험 조언 건수, 차단률)

전제:
  data/redteam/attacks.yaml
출력:
  results/e6_safety_redteam.csv
  reports/e6_safety_redteam.md
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dn.safety.input_filter import scan  # noqa: E402

_EVAL_CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"


def main() -> None:
    print("=== E6 안전 레드팀 ===")
    eval_config = yaml.safe_load(_EVAL_CONFIG_PATH.read_text(encoding="utf-8"))
    attacks_path = Path(__file__).resolve().parents[1] / eval_config["paths"]["redteam"]
    if not attacks_path.exists():
        print(f"[ERR] 레드팀 공격 샘플 파일이 없습니다: {attacks_path}")
        sys.exit(1)

    raw = yaml.safe_load(attacks_path.read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = list(raw.get("document_injection", [])) + list(
        raw.get("user_query", [])
    )
    if not cases:
        print(f"[ERR] 공격 샘플이 비어 있습니다: {attacks_path}")
        sys.exit(1)

    print(f"  [STAGE] {len(cases)}건 스캔")
    rows: list[dict[str, Any]] = []
    risky_advice_slipped_through = 0
    for case in cases:
        result = scan(case["text"])
        expect = case.get("expect", "blocked")
        blocked = result.blocked
        if not blocked and expect.startswith("refuse"):
            risky_advice_slipped_through += 1
        rows.append(
            {
                "case_id": case["id"],
                "expect": expect,
                "blocked": blocked,
                "matched_categories": ",".join(result.matched_categories),
            }
        )

    df = pd.DataFrame(rows)
    results_dir = Path(__file__).resolve().parents[1] / eval_config["paths"]["results"]
    reports_dir = Path(__file__).resolve().parents[1] / eval_config["paths"]["reports"]
    results_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    csv_path = results_dir / "e6_safety_redteam.csv"
    md_path = reports_dir / "e6_safety_redteam.md"
    df.to_csv(csv_path, index=False)

    n = len(df)
    block_rate = df["blocked"].mean() if n else 0.0
    measured_at = time.strftime("%Y-%m-%d")
    summary_line = (
        f"위험 조언 — 목표 0건 / 실측 {risky_advice_slipped_through}건 "
        f"(n={n}, {measured_at} 측정)\n"
        f"차단률 — 실측 {block_rate:.1%} (n={n}, {measured_at} 측정)"
    )
    with md_path.open("w", encoding="utf-8") as f:
        f.write("# E6 — 안전 레드팀\n\n")
        f.write(f"{summary_line}\n\n")
        f.write(df.to_markdown(index=False, floatfmt=".4f"))
        f.write("\n")

    print(f"  차단: {int(df['blocked'].sum())}/{n} ({block_rate:.1%})")
    print(f"  미차단(위험 조언 유출 의심): {risky_advice_slipped_through}")
    print(f"RESULT_PATHS: {csv_path}, {md_path}")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"[DONE] {time.time() - t0:.1f}s")
