"""
사용자 사례 생성기 (기획서 14.2 "공식 조건을 조합한 사용자 사례 100건 이상")

전제:
  없음 (독립 실행)
출력:
  data/cases/*.json (100건 이상)

각 사례는 규칙 엔진 facts 와, 규칙 엔진과 완전히 독립적으로 재구현한
간단한 기준(오라클)으로 계산한 "기대 최우선 경로"를 함께 담는다.
E3(제도 후보 누락률)가 이 오라클과 실제 rules.engine 결과를 대조한다.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import yaml

SEED = 42
_ROOT = Path(__file__).resolve().parents[2]
_EVAL_CONFIG_PATH = _ROOT / "eval" / "config.yaml"


def expected_top_path(facts: dict) -> str | None:
    """rules.engine 을 전혀 참조하지 않는 독립 오라클.

    신용회복위원회 공식 비교 기준(기획서 5단계 원문)만 그대로 재구현한다:
    연체 30일 이하 → 신속채무조정, 31~89일 → 사전채무조정, 90일 이상 → 개인워크아웃.
    법원 절차 진행 중이면 committee 프로그램 대상에서 제외되고 법원 경로가 된다.
    """
    if facts.get("court_proceeding_ongoing"):
        return "court_rehabilitation"
    days = facts.get("max_overdue_days")
    if days is None:
        return None
    if days <= 30:
        return "sinsok_debt_adjustment"
    if days <= 89:
        return "pre_debt_adjustment"
    return "personal_workout"


def _base_facts(rng: np.random.Generator, **overrides) -> dict:
    facts = {
        "max_overdue_days": int(rng.integers(0, 120)),
        "total_debt": int(rng.integers(1_000_000, 60_000_000)),
        "has_continuous_income": True,
        "income_proof_available": True,
        "has_secured_debt": bool(rng.integers(0, 2)),
        "has_overdue": True,
        "income_drop_signal": False,
        "court_proceeding_ongoing": False,
        "seizure_ongoing": False,
        "has_guarantee_debt": False,
        "has_tax_debt": False,
        "has_private_debt": False,
        "legal_dispute": False,
        "monthly_available": int(rng.integers(-500_000, 2_000_000)),
    }
    facts.update(overrides)
    return facts


def main() -> None:
    print("=== 사용자 사례 생성 ===")
    rng = np.random.default_rng(SEED)

    if not _EVAL_CONFIG_PATH.exists():
        print(f"[ERR] eval/config.yaml 이 없습니다: {_EVAL_CONFIG_PATH}")
        sys.exit(1)
    eval_config = yaml.safe_load(_EVAL_CONFIG_PATH.read_text(encoding="utf-8"))
    cases_dir = _ROOT / eval_config["paths"]["cases"]
    cases_dir.mkdir(parents=True, exist_ok=True)

    cases: list[dict] = []
    idx = 0

    def add(facts: dict) -> None:
        nonlocal idx
        idx += 1
        cases.append(
            {
                "case_id": f"case_{idx:03d}",
                "facts": facts,
                "expected_top_path_id": expected_top_path(facts),
            }
        )

    print("  [STAGE] 연체 구간별 기본 사례 (각 구간 20건, 총 60건)")
    for lo, hi in [(0, 30), (31, 89), (90, 120)]:
        for _ in range(20):
            days = int(rng.integers(lo, hi + 1))
            add(_base_facts(rng, max_overdue_days=days))

    print("  [STAGE] 미확인(UNKNOWN) 필드 조합 사례 (20건)")
    for _ in range(20):
        days = int(rng.integers(0, 120))
        add(
            _base_facts(
                rng,
                max_overdue_days=days,
                has_continuous_income=None if rng.integers(0, 2) else True,
                income_proof_available=None if rng.integers(0, 2) else True,
            )
        )

    print("  [STAGE] 법원 절차·복합지원 신호 사례 (20건)")
    for _ in range(10):
        add(_base_facts(rng, court_proceeding_ongoing=True))
    for _ in range(10):
        add(_base_facts(rng, income_drop_signal=True))

    print(f"  [STAGE] {len(cases)}건 기록")
    for case in cases:
        (cases_dir / f"{case['case_id']}.json").write_text(
            json.dumps(case, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print(f"  matched: {len(cases):,}")
    print(f"RESULT_PATHS: {cases_dir}")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"[DONE] {time.time() - t0:.1f}s")
