"""
E4b — LLM 직접 계산 대조 실험 (보고서용 1회성 실험, E1~E6 핵심 지표 아님)

"계산을 LLM에 맡기면 왜 위험한가"는 지금까지 주장으로만 존재했다. 이 스크립트는
같은 골든 케이스(tests/golden/*.yaml)를 코드(cashflow.calculator.compute, 결정론적
순수 함수)와 LLM에게 각각 계산시켜 오차와 재현성을 직접 대조한다.

docs/고도화_아이디어.md 의 "LLM 대조 실험"에 해당한다. **운영 기능이 아니다** —
`src/dn/rules/counterfactual.py` 의 이중검증 추출(운영 신뢰도용, 별도 계획)과
목적이 다르니 혼동하지 말 것.

측정 두 가지:
  1. 정확도 — 같은 입력에서 LLM이 계산한 4개 값(총채무액/월총상환액/월가용재원/
     월부족액)이 코드 계산(정답) 대비 얼마나 벗어나는가.
  2. 재현성 — 같은 입력을 두 번 넣었을 때 LLM이 매번 같은 값을 내는가. 금융
     계산에서는 정확도만큼 재현성이 중요하다 — 코드는 이 실험 없이도 항상
     재현되지만(순수 함수), LLM은 그렇다는 보장이 없다.

전제:
  tests/golden/*.yaml
출력:
  results/e4b_llm_direct_calc.csv
  reports/e4b_llm_direct_calc.md

주의(정직성 고지): `ANTHROPIC_API_KEY`/`DN_OPENAI_*`/로컬 모델이 전부 없으면
`StubClient` 로 폴백되며, 이 경우 실제 LLM 계산 성능을 측정하지 않는다.
STUB_MODE 여부를 결과에 항상 명시한다.
"""

from __future__ import annotations

import json
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dn.llm.client import StubClient, get_llm_client  # noqa: E402
from dn.llm.schema_call import call_json  # noqa: E402
from dn.settings import get_settings  # noqa: E402

_EVAL_CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"
_FIELDS = ["total_debt", "monthly_total_payment", "monthly_available", "monthly_shortfall"]

_SYSTEM_PROMPT = (
    "당신은 채무 상환여력을 계산하는 보조자다. 아래 4개 공식만 그대로 적용해 "
    "정수(원 단위)로 계산하고, 값이 없는 항목은 0으로 취급한다. 풀이 과정 없이 "
    "JSON으로만 답한다.\n"
    "- total_debt = 모든 채무 잔액의 합\n"
    "- monthly_total_payment = 모든 채무 월상환액의 합\n"
    "- monthly_available = 월 실수령소득 + 정기 지원금 - 필수생활비 - 주거비 "
    "- 의료·돌봄비 - 기타 필수 고정비\n"
    "- monthly_shortfall = monthly_total_payment - monthly_available"
)

_SCHEMA = {
    "type": "object",
    "properties": {f: {"type": "integer"} for f in _FIELDS},
    "required": _FIELDS,
}


def _eval_client() -> tuple[Any, bool]:
    settings = get_settings()
    client = get_llm_client(settings)
    if isinstance(client, StubClient):
        return StubClient(response=json.dumps(dict.fromkeys(_FIELDS, 0))), True
    return client, False


def _debt_line(raw: dict[str, Any], index: int) -> str:
    creditor = raw.get("creditor", f"채무 {index + 1}")
    balance = raw.get("balance")
    payment = raw.get("monthly_payment")
    parts = [f"{creditor}: 잔액 {balance if balance is not None else '없음'}원"]
    parts.append(f"월상환액 {payment if payment is not None else '없음'}원")
    return " / ".join(parts)


def _user_prompt(case: dict[str, Any]) -> str:
    debts = case["input"]["debts"]
    income = case["input"].get("income") or {}
    household = case["input"].get("household") or {}
    lines = ["[채무 목록]"]
    lines += [f"- {_debt_line(d, i)}" for i, d in enumerate(debts)] or ["- 없음"]
    lines.append("[소득]")
    lines.append(f"- 월 실수령소득: {income.get('monthly_net_income', '없음')}원")
    lines.append(f"- 정기 지원금: {income.get('support_income', '없음')}원")
    lines.append("[가구 지출]")
    lines.append(f"- 필수생활비: {household.get('essential_living_cost', '없음')}원")
    lines.append(f"- 주거비: {household.get('housing_cost', '없음')}원")
    lines.append(f"- 의료·돌봄비: {household.get('medical_care_cost', '없음')}원")
    lines.append(f"- 기타 필수 고정비: {household.get('other_fixed_cost', '없음')}원")
    return "\n".join(lines)


def _call_once(client: Any, prompt: str) -> dict[str, int] | None:
    try:
        return call_json(client, system=_SYSTEM_PROMPT, user=prompt, schema=_SCHEMA)
    except Exception as exc:  # noqa: BLE001 - 실험 스크립트, 실패도 결과로 기록
        print(f"    [WARN] LLM 호출 실패: {exc}")
        return None


def main() -> None:
    print("=== E4b LLM 직접 계산 대조 실험 (참고용, E1~E6 핵심 지표 아님) ===")
    eval_config = yaml.safe_load(_EVAL_CONFIG_PATH.read_text(encoding="utf-8"))
    interval = eval_config.get("llm_call_interval_sec", 0)
    golden_dir = Path(__file__).resolve().parents[1] / eval_config["paths"]["golden"]
    golden_files = sorted(p for p in golden_dir.glob("*.yaml"))

    client, stub_mode = _eval_client()
    if stub_mode:
        print("  [경고] LLM 백엔드 미설정 — StubClient 로 대체, 실측 아님(STUB_MODE)")

    rows: list[dict[str, Any]] = []
    for i, path in enumerate(golden_files):
        case = yaml.safe_load(path.read_text(encoding="utf-8"))
        if "expected" not in case:
            continue
        expected = case["expected"]
        prompt = _user_prompt(case)

        print(f"  [{case['id']}] 1차 호출")
        first = _call_once(client, prompt)
        if not stub_mode and interval and i < len(golden_files) - 1:
            time.sleep(interval)
        print(f"  [{case['id']}] 2차 호출 (재현성 대조용)")
        second = _call_once(client, prompt)
        if not stub_mode and interval and i < len(golden_files) - 1:
            time.sleep(interval)

        max_error = None
        if first is not None:
            max_error = max(abs(int(first[f]) - int(Decimal(str(expected[f])))) for f in _FIELDS)
        reproducible = first is not None and second is not None and first == second

        rows.append(
            {
                "case_id": case["id"],
                "call1_max_abs_error_won": max_error,
                "call1_response": json.dumps(first, ensure_ascii=False),
                "call2_response": json.dumps(second, ensure_ascii=False),
                "reproducible": reproducible,
            }
        )

    df = pd.DataFrame(rows)
    results_dir = Path(__file__).resolve().parents[1] / eval_config["paths"]["results"]
    reports_dir = Path(__file__).resolve().parents[1] / eval_config["paths"]["reports"]
    results_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    csv_path = results_dir / "e4b_llm_direct_calc.csv"
    md_path = reports_dir / "e4b_llm_direct_calc.md"
    df.to_csv(csv_path, index=False)

    n = len(df)
    measured_at = time.strftime("%Y-%m-%d")
    stub_note = " [STUB_MODE: 실제 LLM 미사용, 참고용 수치임]" if stub_mode else ""
    errors = df["call1_max_abs_error_won"].dropna()
    max_error_overall = int(errors.max()) if len(errors) else "N/A"
    n_reproducible = int(df["reproducible"].sum())
    summary_line = (
        f"LLM 직접 계산 오차 — 코드(결정론적 계산 모듈) 대비 최대오차 "
        f"{max_error_overall}원 (n={n}, {measured_at} 측정){stub_note}\n"
        f"재현성 — 동일 입력 2회 호출 결과 완전 일치 {n_reproducible}/{n}건{stub_note}"
    )
    with md_path.open("w", encoding="utf-8") as f:
        f.write("# E4b — LLM 직접 계산 대조 실험\n\n")
        f.write(
            "**참고용 1회성 실험이다.** E1~E6 핵심 지표에 포함되지 않는다 — "
            '"계산은 코드가 전담해야 하는 이유"의 증거 자료로만 쓴다.\n\n'
        )
        f.write(f"{summary_line}\n\n")
        f.write(df.to_markdown(index=False))
        f.write("\n")

    print(f"  정확도: 최대오차 {max_error_overall}원 (n={n}){stub_note}")
    print(f"  재현성: {n_reproducible}/{n}건 완전 일치{stub_note}")
    print(f"RESULT_PATHS: {csv_path}, {md_path}")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"[DONE] {time.time() - t0:.1f}s")
