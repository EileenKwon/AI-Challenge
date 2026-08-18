"""T04 — 로그 감사 필터 테스트."""

from __future__ import annotations

from dn.safety.audit import redact


def test_document_text_key_is_fully_redacted() -> None:
    payload = {"session_id": "s1", "raw_text": "주민번호 900101-1234567 포함 원문"}
    result = redact(payload)
    assert result["raw_text"] == "[REDACTED]"
    assert result["session_id"] == "s1"


def test_nested_pii_in_non_sensitive_keys_is_masked() -> None:
    payload = {"note": "연락처 010-1234-5678 로 회신 바랍니다"}
    result = redact(payload)
    assert "010-1234-5678" not in result["note"]


def test_lists_are_recursively_redacted() -> None:
    payload = {"notes": ["연락처 010-1234-5678", "정상 텍스트"]}
    result = redact(payload)
    assert "010-1234-5678" not in result["notes"][0]
    assert result["notes"][1] == "정상 텍스트"


def test_non_string_values_pass_through() -> None:
    payload = {"field_count": 5, "confirmed": True}
    result = redact(payload)
    assert result == payload


def test_original_object_is_not_mutated() -> None:
    payload = {"raw_text": "원문"}
    redact(payload)
    assert payload["raw_text"] == "원문"
