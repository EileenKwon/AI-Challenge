"""
E7 — 사용자 이해도 · 준비시간 (사용자 스터디 집계)

전제:
  eval/user_study/responses.csv  (없으면 아무것도 하지 않고 종료한다)
출력:
  reports/e7_user_study.md

E1~E6 과 달리 이 지표는 사람이 있어야 측정된다. 이 스크립트는 측정을 하지 않고
**수집된 응답을 집계만** 한다. 응답 파일이 없으면 리포트를 만들지 않으며,
report_builder 는 그 경우 두 지표를 "미측정" 으로 그대로 둔다 — 없는 값을
0 이나 목표치로 채우지 않는다.

절차는 eval/user_study/프로토콜.md 참고.
"""

from __future__ import annotations

import csv
import statistics
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_RESPONSES = _ROOT / "eval" / "user_study" / "responses.csv"
_QUESTIONS = ("q1", "q2", "q3", "q4", "q5")


def main() -> None:
    print("=== E7 사용자 스터디 집계 ===")
    if not _RESPONSES.exists():
        print(f"  [SKIP] 응답 파일이 없습니다: {_RESPONSES}")
        print("         eval/user_study/프로토콜.md 절차로 수집한 뒤 다시 실행하세요.")
        print("         (지표는 '미측정' 으로 유지됩니다 — 임의의 값으로 채우지 않습니다)")
        return

    rows = [r for r in csv.DictReader(_RESPONSES.open(encoding="utf-8")) if r.get("participant")]
    if not rows:
        print(f"  [ERR] 응답이 비어 있습니다: {_RESPONSES}")
        sys.exit(1)

    n = len(rows)
    print(f"  참가자 {n}명")

    # --- 이해도: 문항 평균의 참가자 평균 ---
    per_participant = []
    per_question: dict[str, list[float]] = {q: [] for q in _QUESTIONS}
    for row in rows:
        scores = []
        for q in _QUESTIONS:
            value = float(row[q])
            scores.append(value)
            per_question[q].append(value)
        per_participant.append(statistics.mean(scores))
    comprehension = statistics.mean(per_participant)

    # --- 준비시간: 참가자별 단축률의 평균 ---
    reductions = []
    for row in rows:
        manual = float(row["manual_seconds"])
        service = float(row["service_seconds"])
        if manual <= 0:
            continue
        reductions.append((manual - service) / manual)
    reduction = statistics.mean(reductions) if reductions else 0.0

    # --- 원칙 전달 실패 신호 ---
    felt_certified = sum(
        1 for r in rows if (r.get("felt_certified") or "").strip().lower() == "yes"
    )

    measured_at = time.strftime("%Y-%m-%d")
    summary = (
        f"사용자 이해도 — 목표 평균 4점 이상(5점 척도) / 실측 {comprehension:.2f}점 "
        f"(n={n}, {measured_at} 측정)\n"
        f"준비시간 — 목표 수동 정리 대비 30% 이상 단축 / 실측 {reduction:.1%} 단축 "
        f"(n={n}, {measured_at} 측정)"
    )

    reports_dir = _ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    md_path = reports_dir / "e7_user_study.md"
    with md_path.open("w", encoding="utf-8") as f:
        f.write("# E7 — 사용자 이해도 · 준비시간\n\n")
        f.write(f"{summary}\n\n")
        f.write("## 문항별 평균\n\n| 문항 | 측정 대상 | 평균 |\n|---|---|---|\n")
        labels = {
            "q1": "확정 숫자의 전달",
            "q2": "확정/후보 구분 — 핵심 원칙",
            "q3": "판정 근거의 전달",
            "q4": "미확인 조건의 전달",
            "q5": "실행 안내의 전달",
        }
        for q in _QUESTIONS:
            f.write(f"| {q.upper()} | {labels[q]} | {statistics.mean(per_question[q]):.2f} |\n")
        f.write("\n## 준비시간\n\n")
        f.write("| 참가자 | 순서 | 수동(초) | 서비스(초) | 단축률 |\n|---|---|---|---|---|\n")
        for row in rows:
            manual, service = float(row["manual_seconds"]), float(row["service_seconds"])
            rate = (manual - service) / manual if manual > 0 else 0.0
            f.write(
                f"| {row['participant']} | {row.get('order', '')} | {manual:.0f} | "
                f"{service:.0f} | {rate:.1%} |\n"
            )
        f.write(
            "\n> 순서(`AB`/`BA`)를 섞은 이유: 같은 문서를 두 번째로 다룰 때는 내용을 이미 "
            "알고 있어 무조건 빨라진다. 순서를 고정하면 그 학습 효과가 서비스의 성과로 "
            "둔갑한다.\n"
        )
        if felt_certified:
            f.write(
                f"\n> ⚠️ **원칙 전달 실패 {felt_certified}건** — 참가자가 이 서비스가 신청 자격을 "
                "확정해 준다고 느꼈다고 답했다. '제도는 후보' 원칙이 화면에서 전달되지 "
                "않았다는 뜻이므로 문항 점수와 별개로 다뤄야 한다.\n"
            )
        notes = [r["note"] for r in rows if (r.get("note") or "").strip()]
        if notes:
            f.write("\n## 자유 응답\n\n")
            for note in notes:
                f.write(f"- {note}\n")

    print(f"  이해도 평균: {comprehension:.2f} / 5")
    print(f"  준비시간 단축: {reduction:.1%}")
    if felt_certified:
        print(f"  [WARN] '자격을 확정해 준다고 느꼈다' {felt_certified}건 — 원칙 전달 실패")
    print(f"RESULT_PATHS: {md_path}")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"[DONE] {time.time() - t0:.1f}s")
