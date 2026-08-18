"""
E2 — 핵심 숫자 추출 정확도 (잔액·연체일수)

전제:
  data/synthetic/pdf/*.pdf
  data/synthetic/labels/*.json
출력:
  results/e2_number_accuracy.csv
  reports/e2_number_accuracy.md

주의(정직성 고지): E1 과 동일하게 ANTHROPIC_API_KEY 미설정 시 StubClient
(빈 응답)로 폴백하며, 이 경우 실제 LLM 성능을 측정하지 않는다.
"""

from __future__ import annotations

import json
import sys
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dn.extraction.extractor import extract  # noqa: E402
from dn.ingest import pdf_reader  # noqa: E402
from dn.llm.client import StubClient, get_llm_client  # noqa: E402
from dn.settings import get_settings  # noqa: E402

SEED = 42
_EVAL_CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"


def _eval_client() -> tuple[Any, bool]:
    settings = get_settings()
    client = get_llm_client(settings)
    if isinstance(client, StubClient):
        return StubClient(response='{"debts": []}'), True
    return client, False


def _label_int(raw: dict[str, Any], field: str) -> int | None:
    value = raw.get(field)
    if value is None:
        return None
    if field == "balance":
        try:
            return int(Decimal(str(value)))
        except InvalidOperation:
            return None
    return int(value)


def main() -> None:
    print("=== E2 핵심 숫자 추출 정확도 ===")
    np.random.default_rng(SEED)

    eval_config = yaml.safe_load(_EVAL_CONFIG_PATH.read_text(encoding="utf-8"))
    root = Path(__file__).resolve().parents[1]
    pdf_dir = root / eval_config["paths"]["synthetic_pdf"]
    label_dir = root / eval_config["paths"]["synthetic_labels"]
    fields: list[str] = eval_config["e2"]["fields"]

    if not pdf_dir.exists() or not any(pdf_dir.glob("*.pdf")):
        print(f"[ERR] 합성 PDF 가 없습니다: {pdf_dir}")
        sys.exit(1)
    if not label_dir.exists() or not any(label_dir.glob("*.json")):
        print(f"[ERR] 라벨 파일이 없습니다: {label_dir}")
        sys.exit(1)

    label_files = sorted(label_dir.glob("*.json"))
    print(f"  대상 케이스: {len(label_files)}건")

    client, stub_mode = _eval_client()
    if stub_mode:
        print("  [WARN] ANTHROPIC_API_KEY 미설정 — StubClient(빈 응답)로 실행합니다.")

    per_field_correct = dict.fromkeys(fields, 0)
    per_field_total = dict.fromkeys(fields, 0)
    rows: list[dict[str, Any]] = []

    for label_path in label_files:
        label = json.loads(label_path.read_text(encoding="utf-8"))
        pdf_path = pdf_dir / label["pdf_file"]
        if not pdf_path.exists():
            continue

        document = pdf_reader.read(pdf_path, doc_id=label["case_id"])
        extracted = extract(document, client=client)
        expected_debts = label["debts"]
        n = min(len(extracted), len(expected_debts))

        for i in range(n):
            for field in fields:
                expected = _label_int(expected_debts[i], field)
                if expected is None:
                    continue
                actual = getattr(extracted[i], field).value
                actual_int = int(actual) if actual is not None else None
                per_field_total[field] += 1
                correct = actual_int == expected
                if correct:
                    per_field_correct[field] += 1
                rows.append(
                    {
                        "case_id": label["case_id"],
                        "debt_index": i,
                        "field": field,
                        "expected": expected,
                        "actual": actual_int,
                        "correct": correct,
                    }
                )
        for i in range(n, len(expected_debts)):
            for field in fields:
                expected = _label_int(expected_debts[i], field)
                if expected is None:
                    continue
                per_field_total[field] += 1
                rows.append(
                    {
                        "case_id": label["case_id"],
                        "debt_index": i,
                        "field": field,
                        "expected": expected,
                        "actual": None,
                        "correct": False,
                    }
                )

    df = pd.DataFrame(rows)
    field_summary = pd.DataFrame(
        [
            {
                "field": f,
                "correct": per_field_correct[f],
                "total": per_field_total[f],
                "accuracy": per_field_correct[f] / np.maximum(per_field_total[f], 1),
            }
            for f in fields
        ]
    )

    results_dir = root / eval_config["paths"]["results"]
    reports_dir = root / eval_config["paths"]["reports"]
    results_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    csv_path = results_dir / "e2_number_accuracy.csv"
    md_path = reports_dir / "e2_number_accuracy.md"
    df.to_csv(csv_path, index=False)

    total_correct = sum(per_field_correct.values())
    total_n = sum(per_field_total.values())
    overall_accuracy = total_correct / max(total_n, 1)
    target = eval_config["targets"]["e2_number_accuracy"]
    measured_at = time.strftime("%Y-%m-%d")
    stub_note = " [STUB_MODE: 실제 LLM 미사용]" if stub_mode else ""
    summary_line = (
        f"핵심 숫자 추출 정확도 — 목표 {target} / 실측 {overall_accuracy:.4f} "
        f"(n={total_n}, {measured_at} 측정){stub_note}"
    )

    with md_path.open("w", encoding="utf-8") as f:
        f.write("# E2 — 핵심 숫자 추출 정확도\n\n")
        f.write(f"{summary_line}\n\n")
        f.write(field_summary.to_markdown(index=False, floatfmt=".4f"))
        f.write("\n")

    print(f"  전체 정확도: {overall_accuracy:.4f} ({total_correct}/{total_n})")
    print(f"RESULT_PATHS: {csv_path}, {md_path}")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"[DONE] {time.time() - t0:.1f}s")
