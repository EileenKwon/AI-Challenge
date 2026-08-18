"""LLM 호출 전 개인정보 마스킹.

원본 파일이 아니라 추출된 텍스트에 적용한다. 금융회사명·금액·날짜는
과잉 마스킹으로 추출 성능이 떨어지지 않도록 대상에서 제외한다.

패턴은 우선순위 순서로 적용한다: 앞선 패턴이 이미 치환한 구간은 뒤 패턴이
재매칭하지 않도록(예: 전화번호가 범용 계좌번호 패턴에 잡히지 않도록) 순서가 중요하다.
"""

from __future__ import annotations

import re

from dn.domain.models import MaskReport

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("rrn", re.compile(r"\b\d{6}-[1-4]\d{6}\b")),
    ("card", re.compile(r"\b(?:\d{4}[- ]){3}\d{4}\b")),
    ("phone", re.compile(r"\b0\d{1,2}-\d{3,4}-\d{4}\b")),
    # 계좌번호: 2~6자리 그룹 뒤 마지막 그룹은 3자리 이상으로 제한해
    # "2026-08-13" 같은 날짜(YYYY-MM-DD)를 오탐하지 않게 한다.
    ("account", re.compile(r"\b\d{2,6}-\d{2,6}-\d{3,8}(?:-\d{2,8})?\b")),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("address", re.compile(r"\b\d{1,4}동\s?\d{1,4}호\b|\b\d{1,4}-\d{1,4}번지\b")),
)


def mask(text: str) -> tuple[str, MaskReport]:
    """텍스트에서 PII 를 찾아 `[MASKED:<종류>]` 로 치환하고 유형별 개수를 보고한다."""
    masked_counts: dict[str, int] = {}
    result = text
    for name, pattern in _PATTERNS:
        result, n = pattern.subn(f"[MASKED:{name}]", result)
        if n:
            masked_counts[name] = n
    return result, MaskReport(masked_counts=masked_counts)
