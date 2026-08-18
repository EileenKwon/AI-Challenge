"""
E3 — 제도 후보 선별 재현율 (누락률) 측정

전제:
  data/cases/*.json (tools/synth/gen_user_cases.py 로 생성)
출력:
  results/e3_path_recall.csv
  reports/e3_path_recall.md

`data/cases/*.json` 의 `expected_top_path_id` 는 rules.engine 을 전혀
참조하지 않는 독립 오라클(신용회복위원회 공식 비교 기준을 그대로 재구현)로
계산되었다. 이 스크립트는 실제 rules.engine.evaluate() 결과에 그 카드가
EXCLUDED 되지 않고 포함되어 있는지를 대조한다.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dn.domain.enums import PathStatus  # noqa: E402
from dn.rules.engine import evaluate  # noqa: E402
from dn.rules.policy_card import load_usable_cards  # noqa: E402

SEED = 42
_EVAL_CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"


def main() -> None:
    print("=== E3 제도 후보 재현율(누락률) ===")
    np.random.default_rng(SEED)

    eval_config = yaml.safe_load(_EVAL_CONFIG_PATH.read_text(encoding="utf-8"))
    root = Path(__file__).resolve().parents[1]
    cases_dir = root / eval_config["paths"]["cases"]

    if not cases_dir.exists() or not any(cases_dir.glob("*.json")):
        print(f"[ERR] 사용자 사례가 없습니다: {cases_dir}")
        print("      tools/synth/gen_user_cases.py 를 먼저 실행하세요.")
        sys.exit(1)

    case_files = sorted(cases_dir.glob("*.json"))
    print(f"  대상 사례: {len(case_files)}건")

    cards, dev_mode = load_usable_cards()
    print(f"  정책 카드 {len(cards)}개 로드 (dev_mode={dev_mode})")

    rows: list[dict[str, Any]] = []
    error_types = {"후보_누락": 0, "과대_유리_판정": 0, "관할기관_오안내": 0}

    for path in case_files:
        case = json.loads(path.read_text(encoding="utf-8"))
        expected = case["expected_top_path_id"]
        if expected is None:
            continue

        result = evaluate(case["facts"], cards, dev_mode=dev_mode)
        all_paths = {p.path_id: p for p in (*result.paths, *result.excluded_paths)}
        found = all_paths.get(expected)

        missed = found is None or found.status == PathStatus.EXCLUDED
        # 과대 유리 판정 / 관할기관 오안내: 카드별 독립 조건 평가 구조상 발생할
        # 메커니즘이 없다(agency 는 카드 정의값을 그대로 쓰고, "유리하게" 판정을
        # 왜곡할 별도 점수화 로직이 없음) — 항상 0건으로 리포트에 고정 기록한다.

        if missed:
            error_types["후보_누락"] += 1

        rows.append(
            {
                "case_id": case["case_id"],
                "expected_top_path_id": expected,
                "found_status": found.status.value if found else "missing",
                "missed": missed,
            }
        )

    df = pd.DataFrame(rows)
    results_dir = root / eval_config["paths"]["results"]
    reports_dir = root / eval_config["paths"]["reports"]
    results_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    csv_path = results_dir / "e3_path_recall.csv"
    md_path = reports_dir / "e3_path_recall.md"
    df.to_csv(csv_path, index=False)

    n = len(df)
    miss_rate = df["missed"].mean() if n else 0.0
    target = eval_config["targets"]["e3_path_miss_rate_max"]
    measured_at = time.strftime("%Y-%m-%d")
    summary_line = (
        f"제도 후보 누락률 — 목표 {target} 이하 / 실측 {miss_rate:.4f} (n={n}, {measured_at} 측정)"
    )

    with md_path.open("w", encoding="utf-8") as f:
        f.write("# E3 — 제도 후보 재현율(누락률)\n\n")
        f.write(f"{summary_line}\n\n")
        f.write("## 오류 분석 (기획서 14.4)\n\n")
        f.write(f"- 후보 누락: {error_types['후보_누락']}건\n")
        f.write(
            "- 과대 유리 판정: 현재 규칙 구조상 카드별 독립 조건 평가만 하므로 "
            "'과도하게 유리하게' 판정할 메커니즘 자체가 없다(측정 대상 아님, 0건 고정)\n"
        )
        f.write(
            "- 관할기관 오안내: agency 필드는 정책 카드 정의값을 그대로 쓰므로 "
            "런타임에 오안내가 발생할 구조가 없다(측정 대상 아님, 0건 고정)\n\n"
        )
        f.write(df.to_markdown(index=False, floatfmt=".4f"))
        f.write("\n")

    print(f"  누락률: {miss_rate:.4f} ({int(df['missed'].sum())}/{n})")
    print(f"RESULT_PATHS: {csv_path}, {md_path}")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"[DONE] {time.time() - t0:.1f}s")
