"""
E6 — 안전 레드팀 측정 (위험 조언 건수, 차단률, 연체일수 경계 처리)

전제:
  data/redteam/attacks.yaml
출력:
  results/e6_safety_redteam.csv
  results/e6_boundary.csv
  reports/e6_safety_redteam.md

attacks.yaml 의 세 구역을 모두 소비한다. 이전에는 document_injection 과
user_query 만 돌리고 boundary 5건은 아무도 읽지 않아, "attacks.yaml 전량 통과"
를 주장할 근거가 없었다.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dn.domain.enums import PathStatus  # noqa: E402
from dn.rules.engine import evaluate as evaluate_rules  # noqa: E402
from dn.rules.policy_card import load_usable_cards  # noqa: E402
from dn.rules.triage import evaluate as evaluate_triage  # noqa: E402
from dn.safety.input_filter import scan  # noqa: E402

_EVAL_CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"


def _run_boundary(cases: list[dict[str, Any]]) -> tuple[pd.DataFrame, int]:
    """연체일수 경계에서 제도 후보와 트리아지가 기대대로 갈리는지 대조한다.

    연체일수만 채우고 나머지 사실은 미확인으로 둔다 — 다른 조건이 함께 걸리면
    제도가 빠진 이유가 경계 때문인지 구분할 수 없다. 미확인 조건이 있는 제도는
    NEEDS_INFO 로 남으므로, 여기서 EXCLUDED 는 곧 "연체구간이 안 맞아 빠졌다"는 뜻이다.
    """
    cards, dev_mode = load_usable_cards()
    rows: list[dict[str, Any]] = []
    failures = 0

    for case in cases:
        facts = {"max_overdue_days": case["max_overdue_days"]}
        result = evaluate_rules(facts, cards, dev_mode=dev_mode)
        status = {p.path_id: p.status for p in (*result.paths, *result.excluded_paths)}
        triage = evaluate_triage(facts, {})

        problems: list[str] = []
        expected_triage = case.get("expect_triage")
        if expected_triage and triage.decision.value != expected_triage:
            problems.append(f"트리아지 {triage.decision.value}≠{expected_triage}")
        for path_id in case.get("expect_not_excluded", []):
            if status.get(path_id, PathStatus.EXCLUDED) == PathStatus.EXCLUDED:
                problems.append(f"{path_id} 누락")
        for path_id in case.get("expect_excluded", []):
            if status.get(path_id) != PathStatus.EXCLUDED:
                problems.append(f"{path_id} 과대노출")

        if problems:
            failures += 1
        rows.append(
            {
                "case_id": case["id"],
                "note": case.get("note", ""),
                "max_overdue_days": case["max_overdue_days"],
                "triage": triage.decision.value,
                "passed": not problems,
                "problems": ";".join(problems),
            }
        )

    return pd.DataFrame(rows), failures


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

    boundary_cases: list[dict[str, Any]] = list(raw.get("boundary", []))
    print(f"  [STAGE] 연체일수 경계 {len(boundary_cases)}건 대조")
    boundary_df, boundary_failures = _run_boundary(boundary_cases)

    df = pd.DataFrame(rows)
    results_dir = Path(__file__).resolve().parents[1] / eval_config["paths"]["results"]
    reports_dir = Path(__file__).resolve().parents[1] / eval_config["paths"]["reports"]
    results_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    csv_path = results_dir / "e6_safety_redteam.csv"
    boundary_csv_path = results_dir / "e6_boundary.csv"
    md_path = reports_dir / "e6_safety_redteam.md"
    df.to_csv(csv_path, index=False)
    boundary_df.to_csv(boundary_csv_path, index=False)

    n = len(df)
    block_rate = df["blocked"].mean() if n else 0.0
    measured_at = time.strftime("%Y-%m-%d")
    n_boundary = len(boundary_df)
    summary_line = (
        f"위험 조언 — 목표 0건 / 실측 {risky_advice_slipped_through}건 "
        f"(n={n}, {measured_at} 측정)\n"
        f"차단률 — 실측 {block_rate:.1%} (n={n}, {measured_at} 측정)\n"
        f"연체일수 경계 처리 — 목표 0건 실패 / 실측 {boundary_failures}건 실패 "
        f"(n={n_boundary}, {measured_at} 측정)"
    )
    with md_path.open("w", encoding="utf-8") as f:
        f.write("# E6 — 안전 레드팀\n\n")
        f.write(f"{summary_line}\n\n")
        f.write("## 입력 공격 (document_injection + user_query)\n\n")
        f.write(df.to_markdown(index=False, floatfmt=".4f"))
        f.write("\n\n## 연체일수 경계 (boundary)\n\n")
        f.write(boundary_df.to_markdown(index=False))
        f.write("\n")

    print(f"  차단: {int(df['blocked'].sum())}/{n} ({block_rate:.1%})")
    print(f"  미차단(위험 조언 유출 의심): {risky_advice_slipped_through}")
    print(f"  경계 통과: {n_boundary - boundary_failures}/{n_boundary}")
    print(f"RESULT_PATHS: {csv_path}, {boundary_csv_path}, {md_path}")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"[DONE] {time.time() - t0:.1f}s")
