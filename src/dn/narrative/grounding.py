"""숫자 그라운딩 검증 — LLM 문장에 허용되지 않은 숫자가 등장하면 실패시킨다.

"4,600만 원", "46,000,000원", "4600만원" 같은 표기 변형을 전부 `Decimal` 로
정규화해 허용 집합과 대조한다. 허용 집합 구성은 `generator.py` 가 담당한다.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from dn.domain.models import GroundingReport

GroundingSet = frozenset[Decimal]

_TOKEN_RE = re.compile(
    r"(?P<eok_man>-?\d[\d,]*\s*억\s*\d[\d,]*\s*만\s*원?)"
    r"|(?P<eok_only>-?\d[\d,]*\s*억\s*원?)"
    r"|(?P<man>-?\d[\d,]*\s*만\s*원?)"
    r"|(?P<percent>-?\d+(?:\.\d+)?\s*%)"
    r"|(?P<plain_won>-?\d[\d,]*(?:\.\d+)?\s*원)"
    r"|(?P<bare>-?\d[\d,]*(?:\.\d+)?)"
)
_DIGIT_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def _clean_decimal(s: str) -> Decimal:
    return Decimal(s.replace(",", ""))


def _first_number(s: str) -> Decimal:
    match = _DIGIT_RE.search(s)
    if not match:
        raise InvalidOperation(s)
    return _clean_decimal(match.group())


def _normalize_token(kind: str, raw: str) -> Decimal:
    if kind == "eok_man":
        numbers = _DIGIT_RE.findall(raw)
        eok, man = _clean_decimal(numbers[0]), _clean_decimal(numbers[1])
        return eok * Decimal("100000000") + man * Decimal("10000")
    if kind == "eok_only":
        return _first_number(raw) * Decimal("100000000")
    if kind == "man":
        return _first_number(raw) * Decimal("10000")
    if kind == "percent":
        return _first_number(raw) / Decimal("100")
    if kind in ("plain_won", "bare"):
        return _first_number(raw)
    raise ValueError(f"알 수 없는 토큰 종류: {kind}")


def extract_number_tokens(text: str) -> list[tuple[str, Decimal]]:
    """텍스트에서 숫자 표현을 찾아 (원문, 정규화된 `Decimal`) 목록으로 반환한다."""
    tokens: list[tuple[str, Decimal]] = []
    for match in _TOKEN_RE.finditer(text):
        kind = match.lastgroup
        raw = match.group()
        try:
            value = _normalize_token(kind, raw)
        except InvalidOperation:
            continue
        tokens.append((raw, value))
    return tokens


def validate_grounding(text: str, allowed: GroundingSet) -> GroundingReport:
    """텍스트에 등장하는 모든 숫자가 `allowed` 안에 있는지 검사한다."""
    ungrounded = [raw for raw, value in extract_number_tokens(text) if value not in allowed]
    return GroundingReport(grounded=not ungrounded, ungrounded_tokens=tuple(ungrounded))
