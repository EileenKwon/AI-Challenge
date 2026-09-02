"""LLM 응답에 JSON 스키마를 강제하는 단일 호출 지점."""

from __future__ import annotations

import json
import logging

import jsonschema

from dn.domain.errors import ExtractionError
from dn.llm.client import LLMClient

logger = logging.getLogger(__name__)


def call_json(
    client: LLMClient,
    *,
    system: str,
    user: str,
    schema: dict,
    max_retries: int = 2,
    max_tokens: int = 1024,
) -> dict:
    """`client` 를 호출해 `schema` 를 만족하는 dict 를 얻는다.

    검증 실패 시 `max_retries` 회까지 재시도하고, 최종 실패하면 `ExtractionError` 를 던진다.
    """
    last_error: Exception | None = None
    total_attempts = max_retries + 1
    for attempt in range(1, total_attempts + 1):
        raw = client.complete(system=system, user=user, max_tokens=max_tokens, json_mode=True)
        try:
            data = json.loads(raw)
            jsonschema.validate(instance=data, schema=schema)
        except (json.JSONDecodeError, jsonschema.ValidationError) as exc:
            last_error = exc
            logger.warning("llm_json_schema_retry", extra={"attempt": attempt})
            continue
        return data

    raise ExtractionError(
        f"LLM 응답이 {total_attempts}회 시도 후에도 스키마를 만족하지 못했습니다."
    ) from last_error
