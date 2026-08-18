"""로그 기록 전 PII·문서 원문 필터.

AGENTS.md 절대 규칙 7: PII 와 문서 원문을 로그에 남기지 않는다.
문서 원문이 실릴 가능성이 있는 키는 값을 통째로 가리고, 그 외 문자열 값은
`pii_masker.mask()` 로 한 번 더 걸러낸다.
"""

from __future__ import annotations

from typing import Any

from dn.ingest.pii_masker import mask

_REDACT_ENTIRE_VALUE_KEYS = frozenset(
    {
        "raw_text",
        "document_text",
        "text",
        "page_text",
        "content",
        "rrn",
        "ssn",
        "account_number",
    }
)


def redact(obj: Any) -> Any:
    """로깅 전 재귀적으로 민감 정보를 제거한 사본을 반환한다. 원본은 변경하지 않는다."""
    if isinstance(obj, dict):
        return {
            key: ("[REDACTED]" if key in _REDACT_ENTIRE_VALUE_KEYS else redact(value))
            for key, value in obj.items()
        }
    if isinstance(obj, (list, tuple)):
        return type(obj)(redact(item) for item in obj)
    if isinstance(obj, str):
        masked_text, _ = mask(obj)
        return masked_text
    return obj
