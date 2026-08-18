"""추출 결과 정규화 — 필드 동의어 통합, 채무유형 매핑, 금액 문자열 파싱."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path

import yaml

from dn.domain.enums import ProductType

_SYNONYMS_PATH = Path(__file__).resolve().parent / "synonyms.yaml"

_PRODUCT_TYPE_KEYWORDS: tuple[tuple[str, ProductType], ...] = (
    ("신용대출", ProductType.CREDIT_LOAN),
    ("신용 대출", ProductType.CREDIT_LOAN),
    ("카드론", ProductType.CARD_LOAN),
    ("현금서비스", ProductType.CASH_ADVANCE),
    ("현금 서비스", ProductType.CASH_ADVANCE),
    ("할부금융", ProductType.INSTALLMENT),
    ("할부 금융", ProductType.INSTALLMENT),
    ("리볼빙", ProductType.REVOLVING),
    ("담보대출", ProductType.SECURED_LOAN),
    ("담보 대출", ProductType.SECURED_LOAN),
    ("보증채무", ProductType.GUARANTEE),
    ("보증 채무", ProductType.GUARANTEE),
)


@lru_cache(maxsize=1)
def _load_field_synonyms() -> dict[str, str]:
    """`synonyms.yaml` 을 "동의어 → 표준 필드명" 평면 딕셔너리로 로드한다."""
    raw: dict[str, list[str]] = yaml.safe_load(_SYNONYMS_PATH.read_text(encoding="utf-8")) or {}
    mapping: dict[str, str] = {}
    for canonical, variants in raw.items():
        mapping[canonical] = canonical
        for variant in variants:
            mapping[variant] = canonical
    return mapping


def normalize_field_name(raw_label: str) -> str | None:
    """문서상 필드 라벨을 표준 필드명으로 변환한다. 알 수 없으면 `None`."""
    return _load_field_synonyms().get(raw_label.strip())


def normalize_product_type(raw_type: str | None) -> ProductType | None:
    """채무유형 원문 표기를 `ProductType` 으로 정규화한다.

    문서에 값 자체가 없으면(`raw_type` 이 비어 있으면) `None` 을 유지해 결측을 전파한다.
    값은 있으나 알려진 분류에 없으면 `OTHER` 를 반환한다.
    """
    if not raw_type or not raw_type.strip():
        return None
    normalized = raw_type.strip()
    for keyword, product_type in _PRODUCT_TYPE_KEYWORDS:
        if keyword in normalized:
            return product_type
    return ProductType.OTHER


_MONEY_CLEAN_RE = re.compile(r"[,\s원]")
_MAN_WON_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*만\s*원?$")


def parse_money(raw: str | None) -> Decimal | None:
    """ "25,000,000원", "2500만원" 같은 문자열을 원 단위 `Decimal` 로 파싱한다.

    파싱에 실패하면 추정하지 않고 `None` 을 반환한다 (AGENTS.md 절대 규칙 2).
    """
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None

    man_match = _MAN_WON_RE.match(text)
    if man_match:
        try:
            return (Decimal(man_match.group(1)) * Decimal("10000")).to_integral_value()
        except InvalidOperation:
            return None

    cleaned = _MONEY_CLEAN_RE.sub("", text)
    if not re.fullmatch(r"\d+", cleaned):
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None
