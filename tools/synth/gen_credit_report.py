"""
합성 신용정보조회서 생성기

전제:
  없음 (독립 실행)
출력:
  data/synthetic/pdf/*.pdf     (50건 이상)
  data/synthetic/labels/*.json (pdf와 1:1 대응하는 정답 라벨)

실제 개인정보를 사용하지 않는다. 전부 가상 인물·가상 금융회사명이다.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import weasyprint
import yaml

SEED = 42

_ROOT = Path(__file__).resolve().parents[2]
_CONFIG_PATH = _ROOT / "eval" / "config.yaml"

_SYLLABLES = list("가나다라마바사아자차카타파하고노도로모보소오조초코토포호")
_INSTITUTION_SUFFIXES = ["은행", "카드", "캐피탈", "저축은행", "파이낸스", "신용조합"]

_PRODUCT_LABELS: dict[str, str] = {
    "credit_loan": "신용대출",
    "card_loan": "카드론",
    "cash_advance": "현금서비스",
    "installment": "할부금융",
    "revolving": "리볼빙",
    "secured_loan": "담보대출",
    "guarantee": "보증채무",
}

# 서식 변형 2종 이상 — 필드 라벨 표기를 다르게 쓴다 (synonyms.yaml 과 맞춘다).
_FORMAT_VARIANTS: dict[str, dict[str, str]] = {
    "A": {
        "creditor": "금융회사명",
        "product_type": "채무유형",
        "balance": "대출잔액",
        "executed_at": "대출실행일",
        "overdue_days": "연체일수",
        "is_secured": "담보여부",
    },
    "B": {
        "creditor": "채권자",
        "product_type": "상품구분",
        "balance": "채무잔액",
        "executed_at": "실행일자",
        "overdue_days": "연체기간",
        "is_secured": "담보유무",
    },
    "C": {
        "creditor": "거래기관",
        "product_type": "대출종류",
        "balance": "원금잔액",
        "executed_at": "개설일",
        "overdue_days": "연체 일수",
        "is_secured": "담보구분",
    },
}


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _build_pdf_from_lines(lines: list[str]) -> bytes:
    """텍스트 라인 목록을 PDF 1페이지로 렌더링한다.

    한글이 포함되므로 손으로 조립한 Type1(Helvetica, 라틴 전용) PDF 대신
    WeasyPrint 를 쓴다 — 시스템에 설치된 Noto Sans CJK KR 로 정확히
    렌더링·추출된다(T17 에서 이미 검증됨).
    """
    body = "<br/>".join(_escape_html(line) if line else "&nbsp;" for line in lines)
    html = (
        "<html><head><meta charset='utf-8'/><style>"
        "body{font-family:'Noto Sans CJK KR',sans-serif;font-size:11pt;"
        "white-space:pre-wrap;margin:20pt;}"
        "</style></head><body>" + body + "</body></html>"
    )
    return weasyprint.HTML(string=html).write_pdf()


def _gen_creditor_name(rng: np.random.Generator) -> str:
    prefix = "".join(rng.choice(_SYLLABLES, size=2))
    suffix = rng.choice(_INSTITUTION_SUFFIXES)
    return f"{prefix}{suffix}"


def _gen_debt(
    rng: np.random.Generator,
    *,
    overdue_days: int | None = None,
    is_secured: bool | None = None,
    product_type: str | None = None,
    omit_fields: set[str] | None = None,
) -> dict:
    omit_fields = omit_fields or set()
    year = int(rng.integers(2019, 2026))
    month = int(rng.integers(1, 13))
    day = int(rng.integers(1, 28))
    debt = {
        "creditor": _gen_creditor_name(rng),
        "product_type": str(product_type or rng.choice(list(_PRODUCT_LABELS))),
        "balance": int(rng.integers(1_000_000, 50_000_000) // 10_000 * 10_000),
        "executed_at": f"{year}-{month:02d}-{day:02d}",
        "overdue_days": overdue_days if overdue_days is not None else int(rng.integers(0, 95)),
        "is_secured": is_secured if is_secured is not None else bool(rng.integers(0, 2)),
    }
    for field in omit_fields:
        debt[field] = None
    return debt


def _render_case(case_id: str, variant: str, debts: list[dict], meta_flags: dict) -> list[str]:
    labels = _FORMAT_VARIANTS[variant]
    lines = [
        "신용정보조회서 (합성 데모용 문서 — 크레딧포유 발급 양식 모사)",
        f"문서번호: {case_id}",
        "조회대상: 합성인물 (실제 개인정보 아님)",
        "",
        "[채무 내역]",
    ]
    for i, d in enumerate(debts, start=1):
        lines.append(f"{i}. {labels['creditor']}: {d['creditor']}")
        if d["product_type"] is not None:
            lines.append(f"   {labels['product_type']}: {_PRODUCT_LABELS[d['product_type']]}")
        if d["balance"] is not None:
            lines.append(f"   {labels['balance']}: {d['balance']:,}원")
        if d["executed_at"] is not None:
            lines.append(f"   {labels['executed_at']}: {d['executed_at']}")
        if d["overdue_days"] is not None:
            lines.append(f"   {labels['overdue_days']}: {d['overdue_days']}일")
        if d["is_secured"] is not None:
            lines.append(f"   {labels['is_secured']}: {'담보' if d['is_secured'] else '무담보'}")
        lines.append("")

    if meta_flags.get("has_conflict"):
        known_total = sum(d["balance"] for d in debts if d["balance"] is not None)
        fake_total = known_total + 9_999_000  # 의도적으로 불일치시킨 총액
        lines.append(f"[안내] 총 채무 합계(별도 산정): {fake_total:,}원")

    return lines


def _label_for(
    case_id: str, pdf_file: str, variant: str, debts: list[dict], meta_flags: dict
) -> dict:
    return {
        "case_id": case_id,
        "pdf_file": pdf_file,
        "format_variant": variant,
        "meta_flags": meta_flags,
        "debts": debts,
    }


def main() -> None:
    print("=== 합성 신용정보조회서 생성 ===")
    rng = np.random.default_rng(SEED)

    if not _CONFIG_PATH.exists():
        print(f"[ERR] eval/config.yaml 이 없습니다: {_CONFIG_PATH}")
        sys.exit(1)
    eval_config = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))
    pdf_dir = _ROOT / eval_config["paths"]["synthetic_pdf"]
    label_dir = _ROOT / eval_config["paths"]["synthetic_labels"]
    pdf_dir.mkdir(parents=True, exist_ok=True)
    label_dir.mkdir(parents=True, exist_ok=True)

    cases: list[tuple[str, str, list[dict], dict]] = []

    def add(case_id: str, variant: str, debts: list[dict], **flags) -> None:
        meta_flags = {
            "income_proof_difficult": False,
            "job_loss_or_business_closed": False,
            "has_conflict": False,
        }
        meta_flags.update(flags)
        cases.append((case_id, variant, debts, meta_flags))

    print("  [STAGE] 경계값·필수 시나리오 생성")
    # 연체일수 경계값 29/30/31/89/90
    for i, days in enumerate([29, 30, 31, 89, 90]):
        add(
            f"boundary_overdue_{days}",
            variant=["A", "B", "C"][i % 3],
            debts=[_gen_debt(rng, overdue_days=days, product_type="credit_loan")],
        )

    # 담보·무담보 혼합
    add(
        "mixed_secured",
        variant="A",
        debts=[
            _gen_debt(rng, is_secured=True, product_type="secured_loan"),
            _gen_debt(rng, is_secured=False, product_type="card_loan"),
            _gen_debt(rng, is_secured=False, product_type="revolving"),
        ],
    )

    # 소득증빙 곤란
    add(
        "income_proof_difficult",
        variant="B",
        debts=[_gen_debt(rng, product_type="credit_loan")],
        income_proof_difficult=True,
    )

    # 실직·폐업
    add(
        "job_loss",
        variant="C",
        debts=[
            _gen_debt(rng, product_type="card_loan"),
            _gen_debt(rng, product_type="cash_advance"),
        ],
        job_loss_or_business_closed=True,
    )

    # 누락 항목 (일부 필드 미기재)
    add(
        "missing_fields",
        variant="A",
        debts=[
            _gen_debt(rng, product_type="installment", omit_fields={"overdue_days"}),
            _gen_debt(rng, product_type="guarantee", omit_fields={"executed_at", "is_secured"}),
        ],
    )

    # 상충 정보 (총액 불일치)
    add(
        "conflicting_total",
        variant="B",
        debts=[
            _gen_debt(rng, product_type="credit_loan"),
            _gen_debt(rng, product_type="card_loan"),
        ],
        has_conflict=True,
    )

    # 채무 1건 ~ 8건 분포 (양 끝 명시적으로 포함)
    for count in [1, 2, 3, 4, 5, 6, 7, 8]:
        add(
            f"debt_count_{count}",
            variant=["A", "B", "C"][count % 3],
            debts=[_gen_debt(rng) for _ in range(count)],
        )

    print("  [STAGE] 나머지 무작위 케이스 생성 (SEED=42)")
    target_total = 55
    idx = 0
    while len(cases) < target_total:
        variant = ["A", "B", "C"][idx % 3]
        debt_count = int(rng.integers(1, 9))
        add(f"random_{idx:03d}", variant=variant, debts=[_gen_debt(rng) for _ in range(debt_count)])
        idx += 1

    print(f"  [STAGE] PDF·라벨 파일 {len(cases)}건 기록")
    for case_id, variant, debts, meta_flags in cases:
        pdf_file = f"{case_id}.pdf"
        lines = _render_case(case_id, variant, debts, meta_flags)
        pdf_bytes = _build_pdf_from_lines(lines)
        (pdf_dir / pdf_file).write_bytes(pdf_bytes)

        label = _label_for(case_id, pdf_file, variant, debts, meta_flags)
        (label_dir / f"{case_id}.json").write_text(
            json.dumps(label, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print(f"  matched: {len(cases):,}")
    print(f"RESULT_PATHS: {pdf_dir}, {label_dir}")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"[DONE] {time.time() - t0:.1f}s")
