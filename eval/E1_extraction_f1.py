"""
E1 — 문서 추출 F1 측정

전제:
  data/synthetic/pdf/*.pdf
  data/synthetic/labels/*.json
출력:
  results/e1_extraction_f1.csv
  reports/e1_extraction_f1.md

주의(정직성 고지): ANTHROPIC_API_KEY 가 설정되지 않은 환경에서는
`StubClient` 로 폴백되며, 이 경우 실제 LLM 추출 성능을 측정하지 않는다
(스텁은 문서를 읽지 않고 빈 결과만 반환한다). 이 스크립트는 API 키가
설정되면 그대로 실제 AnthropicClient 로 동작하도록 작성되어 있다.
STUB_MODE 컬럼/문구로 두 경우를 항상 구분해 표시한다.
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

from dn.domain.models import DocumentContent  # noqa: E402
from dn.extraction.extractor import extract  # noqa: E402
from dn.ingest import pdf_reader  # noqa: E402
from dn.llm.client import StubClient, get_llm_client  # noqa: E402
from dn.settings import get_settings  # noqa: E402

SEED = 42
_EVAL_CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"


def _eval_client() -> tuple[Any, bool]:
    """평가용 LLM 클라이언트. 스텁이면 스키마를 만족하는 빈 응답으로 안전하게 폴백한다."""
    settings = get_settings()
    client = get_llm_client(settings)
    if isinstance(client, StubClient):
        return StubClient(response='{"debts": []}'), True
    return client, False


def _field_value(debt: Any, field: str) -> Any:
    tracked = getattr(debt, field)
    value = tracked.value
    if value is None:
        return None
    if hasattr(value, "value"):  # ProductType 등 enum
        return value.value
    if isinstance(value, Decimal):
        return int(value)
    return str(value) if not isinstance(value, (bool, int)) else value


def _label_value(raw: dict[str, Any], field: str) -> Any:
    value = raw.get(field)
    if value is None:
        return None
    if field == "balance":
        try:
            return int(Decimal(str(value)))
        except InvalidOperation:
            return None
    return value


def main() -> None:
    print("=== E1 문서 추출 F1 ===")
    rng = np.random.default_rng(SEED)
    _ = rng

    eval_config = yaml.safe_load(_EVAL_CONFIG_PATH.read_text(encoding="utf-8"))
    root = Path(__file__).resolve().parents[1]
    pdf_dir = root / eval_config["paths"]["synthetic_pdf"]
    label_dir = root / eval_config["paths"]["synthetic_labels"]
    fields: list[str] = eval_config["e1"]["fields"]

    if not pdf_dir.exists() or not any(pdf_dir.glob("*.pdf")):
        print(f"[ERR] 합성 PDF 가 없습니다: {pdf_dir} (tools/synth/gen_credit_report.py 먼저 실행)")
        sys.exit(1)
    if not label_dir.exists() or not any(label_dir.glob("*.json")):
        print(f"[ERR] 라벨 파일이 없습니다: {label_dir}")
        sys.exit(1)

    label_files = sorted(label_dir.glob("*.json"))
    print(f"  [STAGE] loading labels from {label_dir}")
    print(f"  대상 케이스: {len(label_files)}건")

    client, stub_mode = _eval_client()
    if stub_mode:
        print("  [WARN] ANTHROPIC_API_KEY 미설정 — StubClient(빈 응답)로 실행합니다.")
        print("         이 실행의 F1 은 실제 LLM 추출 성능을 반영하지 않습니다.")

    counts = {f: {"tp": 0, "fp": 0, "fn": 0} for f in fields}
    balance_misextraction = 0
    rows: list[dict[str, Any]] = []

    for label_path in label_files:
        label = json.loads(label_path.read_text(encoding="utf-8"))
        pdf_path = pdf_dir / label["pdf_file"]
        if not pdf_path.exists():
            continue

        document: DocumentContent = pdf_reader.read(pdf_path, doc_id=label["case_id"])
        extracted = extract(document, client=client)
        expected_debts = label["debts"]

        n = min(len(extracted), len(expected_debts))
        for i in range(n):
            for field in fields:
                actual = _field_value(extracted[i], field)
                expected = _label_value(expected_debts[i], field)
                if expected is not None and actual == expected:
                    counts[field]["tp"] += 1
                elif expected is not None:
                    counts[field]["fn"] += 1
                    if field == "balance":
                        balance_misextraction += 1
                elif actual is not None:
                    counts[field]["fp"] += 1
        for i in range(n, len(expected_debts)):
            for field in fields:
                if _label_value(expected_debts[i], field) is not None:
                    counts[field]["fn"] += 1
        for i in range(n, len(extracted)):
            for field in fields:
                if _field_value(extracted[i], field) is not None:
                    counts[field]["fp"] += 1

        rows.append(
            {
                "case_id": label["case_id"],
                "expected_debts": len(expected_debts),
                "extracted_debts": len(extracted),
            }
        )

    print("  [STAGE] 필드별 F1 계산")
    field_rows = []
    for field in fields:
        tp, fp, fn = counts[field]["tp"], counts[field]["fp"], counts[field]["fn"]
        precision = tp / np.maximum(tp + fp, 1)
        recall = tp / np.maximum(tp + fn, 1)
        f1 = 2 * precision * recall / np.maximum(precision + recall, 1e-9)
        field_rows.append(
            {
                "field": field,
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "precision": precision,
                "recall": recall,
                "f1": f1,
            }
        )

    field_df = pd.DataFrame(field_rows)
    case_df = pd.DataFrame(rows)

    results_dir = root / eval_config["paths"]["results"]
    reports_dir = root / eval_config["paths"]["reports"]
    results_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    csv_path = results_dir / "e1_extraction_f1.csv"
    md_path = reports_dir / "e1_extraction_f1.md"
    field_df.to_csv(csv_path, index=False)

    n_cases = len(case_df)
    macro_f1 = field_df["f1"].mean() if len(field_df) else 0.0
    target = eval_config["targets"]["e1_extraction_f1"]
    measured_at = time.strftime("%Y-%m-%d")
    stub_note = " [STUB_MODE: 실제 LLM 미사용, 참고용 수치임]" if stub_mode else ""
    summary_line = (
        f"문서 추출 F1 — 목표 {target} / 실측 {macro_f1:.4f} (n={n_cases}, {measured_at} 측정)"
        f"{stub_note}"
    )

    with md_path.open("w", encoding="utf-8") as f:
        f.write("# E1 — 문서 추출 F1\n\n")
        f.write(f"{summary_line}\n\n")
        f.write("## 오류 분석 (기획서 14.4)\n\n")
        f.write(f"- 금액 오추출: {balance_misextraction}건\n")
        f.write("- 후보 누락 / 과대 유리 판정 / 관할기관 오안내: E3 참조 (제도 후보 관련 오류)\n")
        f.write("- 근거 불일치: E5 참조 (그라운딩 관련 오류)\n\n")
        f.write("## 필드별 F1\n\n")
        f.write(field_df.to_markdown(index=False, floatfmt=".4f"))
        f.write("\n")

    print(f"  macro F1: {macro_f1:.4f}")
    print(f"RESULT_PATHS: {csv_path}, {md_path}")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"[DONE] {time.time() - t0:.1f}s")
