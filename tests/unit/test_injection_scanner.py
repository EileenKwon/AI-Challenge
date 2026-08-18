"""T04 — 인젝션 스캐너 테스트."""

from __future__ import annotations

from pathlib import Path

import yaml

from dn.ingest.injection_scanner import apply, scan

_ATTACKS_PATH = Path(__file__).resolve().parents[2] / "data" / "redteam" / "attacks.yaml"


def _document_injection_cases() -> list[dict]:
    raw = yaml.safe_load(_ATTACKS_PATH.read_text(encoding="utf-8"))
    return raw["document_injection"]


def test_attacks_yaml_has_document_injection_cases() -> None:
    cases = _document_injection_cases()
    assert len(cases) >= 3


def test_all_document_injection_attacks_are_detected() -> None:
    for case in _document_injection_cases():
        report = scan(case["text"])
        assert report.detected is True, f"{case['id']} 가 탐지되지 않았습니다: {case['text']!r}"
        assert case["text"] in report.removed_lines


def test_attack_line_is_removed_from_document_but_rest_kept() -> None:
    case = _document_injection_cases()[0]
    document = f"정상 문단 1\n{case['text']}\n정상 문단 2"
    report = scan(document)
    cleaned = apply(document, report)
    assert case["text"] not in cleaned
    assert "정상 문단 1" in cleaned
    assert "정상 문단 2" in cleaned


def test_document_is_not_rejected_entirely() -> None:
    """인젝션이 있어도 scan()은 예외를 던지지 않고 보고서만 반환한다."""
    case = _document_injection_cases()[0]
    report = scan(case["text"])
    assert report is not None


def test_benign_text_is_not_flagged() -> None:
    report = scan("정상적인 신용정보조회서 내용입니다. A금융 신용대출 잔액 25,000,000원.")
    assert report.detected is False
    assert report.removed_lines == ()
