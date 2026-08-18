"""T05 — LLM JSON 스키마 강제 호출 테스트."""

from __future__ import annotations

import pytest

from dn.domain.errors import ExtractionError
from dn.llm.client import StubClient
from dn.llm.schema_call import call_json

_SCHEMA = {
    "type": "object",
    "properties": {"name": {"type": "string"}},
    "required": ["name"],
}


def test_valid_json_first_try_succeeds() -> None:
    client = StubClient(response='{"name": "A금융"}')
    result = call_json(client, system="sys", user="usr", schema=_SCHEMA)
    assert result == {"name": "A금융"}


def test_invalid_json_then_valid_json_retries_and_succeeds() -> None:
    responses = iter(["not json", '{"name": "B카드"}'])
    client = StubClient(response=lambda system, user: next(responses))
    result = call_json(client, system="sys", user="usr", schema=_SCHEMA, max_retries=2)
    assert result == {"name": "B카드"}


def test_schema_violation_then_valid_retries_and_succeeds() -> None:
    responses = iter(['{"wrong_field": 1}', '{"name": "C캐피탈"}'])
    client = StubClient(response=lambda system, user: next(responses))
    result = call_json(client, system="sys", user="usr", schema=_SCHEMA, max_retries=2)
    assert result == {"name": "C캐피탈"}


def test_final_failure_raises_extraction_error() -> None:
    client = StubClient(response="not json at all")
    with pytest.raises(ExtractionError):
        call_json(client, system="sys", user="usr", schema=_SCHEMA, max_retries=2)


def test_retry_count_is_respected() -> None:
    calls: list[int] = []

    def responder(system: str, user: str) -> str:
        calls.append(1)
        return "not json"

    client = StubClient(response=responder)
    with pytest.raises(ExtractionError):
        call_json(client, system="sys", user="usr", schema=_SCHEMA, max_retries=2)
    assert len(calls) == 3  # 최초 시도 + 재시도 2회


def test_zero_retries_means_single_attempt() -> None:
    calls: list[int] = []

    def responder(system: str, user: str) -> str:
        calls.append(1)
        return "not json"

    client = StubClient(response=responder)
    with pytest.raises(ExtractionError):
        call_json(client, system="sys", user="usr", schema=_SCHEMA, max_retries=0)
    assert len(calls) == 1
