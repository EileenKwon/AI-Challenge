"""T20 — 합성 신용정보조회서 데이터 검증.

생성된 라벨이 `Debt` 스키마와 필드가 일치하는지, 필수 시나리오(연체일수
경계값/담보·무담보 혼합/채무 1~8건/서식 변형 2종 이상 등)가 실제로
포함되어 있는지 확인한다. 파일이 없으면(아직 생성기를 실행하지 않았으면)
건너뛴다 — 이 디렉토리는 `tools/synth/gen_credit_report.py` 실행 산출물이다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dn.domain.enums import ProductType

_ROOT = Path(__file__).resolve().parents[2]
_LABEL_DIR = _ROOT / "data" / "synthetic" / "labels"
_PDF_DIR = _ROOT / "data" / "synthetic" / "pdf"

pytestmark = pytest.mark.skipif(
    not _LABEL_DIR.exists() or not any(_LABEL_DIR.glob("*.json")),
    reason="합성 데이터가 아직 생성되지 않음 (tools/synth/gen_credit_report.py 먼저 실행)",
)


def _load_labels() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(_LABEL_DIR.glob("*.json"))]


def test_at_least_fifty_cases_generated() -> None:
    labels = _load_labels()
    assert len(labels) >= 50


def test_every_label_has_matching_pdf_file() -> None:
    for label in _load_labels():
        assert (_PDF_DIR / label["pdf_file"]).exists()


def test_debt_fields_match_debt_schema() -> None:
    expected_fields = {
        "creditor",
        "product_type",
        "balance",
        "executed_at",
        "overdue_days",
        "is_secured",
    }
    for label in _load_labels():
        for debt in label["debts"]:
            assert set(debt.keys()) == expected_fields, label["case_id"]
            if debt["product_type"] is not None:
                ProductType(debt["product_type"])  # 유효한 enum 값인지 확인


def test_overdue_boundary_cases_present() -> None:
    labels = _load_labels()
    all_overdue_days = {
        d["overdue_days"]
        for label in labels
        for d in label["debts"]
        if d["overdue_days"] is not None
    }
    for boundary in (29, 30, 31, 89, 90):
        assert boundary in all_overdue_days, f"연체일수 {boundary} 경계값 케이스 없음"


def test_mixed_secured_case_present() -> None:
    labels = {label["case_id"]: label for label in _load_labels()}
    mixed = labels["mixed_secured"]
    secured_values = {d["is_secured"] for d in mixed["debts"]}
    assert secured_values == {True, False}


def test_debt_count_range_one_to_eight_covered() -> None:
    labels = _load_labels()
    counts = {len(label["debts"]) for label in labels}
    assert 1 in counts
    assert 8 in counts


def test_missing_fields_case_has_null_values() -> None:
    labels = {label["case_id"]: label for label in _load_labels()}
    missing = labels["missing_fields"]
    all_values = [v for d in missing["debts"] for v in d.values()]
    assert None in all_values


def test_conflicting_total_case_flagged() -> None:
    labels = {label["case_id"]: label for label in _load_labels()}
    assert labels["conflicting_total"]["meta_flags"]["has_conflict"] is True


def test_income_proof_and_job_loss_scenarios_present() -> None:
    labels = {label["case_id"]: label for label in _load_labels()}
    assert labels["income_proof_difficult"]["meta_flags"]["income_proof_difficult"] is True
    assert labels["job_loss"]["meta_flags"]["job_loss_or_business_closed"] is True


def test_at_least_two_format_variants_used() -> None:
    variants = {label["format_variant"] for label in _load_labels()}
    assert len(variants) >= 2


def test_no_real_financial_institution_names() -> None:
    """실존 금융회사명이 아니라 합성 이름인지 대략적으로 확인한다."""
    real_names = {"국민은행", "신한은행", "우리은행", "하나은행", "농협", "카카오뱅크", "토스뱅크"}
    for label in _load_labels():
        for debt in label["debts"]:
            assert debt["creditor"] not in real_names
