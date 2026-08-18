"""신용정보조회서 → `Debt` 목록 추출.

금리·월상환액·상환방식은 이 문서 종류에 존재하지 않으므로 추출하지 않는다
(보완 입력 대상, T06 세부 규칙).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from dn.domain.enums import FieldSource
from dn.domain.models import Debt, DocumentContent
from dn.domain.provenance import Tracked
from dn.extraction.normalizer import normalize_product_type, parse_money
from dn.extraction.prompts import EXTRACTION_SCHEMA, EXTRACTION_SYSTEM_PROMPT, build_user_prompt
from dn.extraction.validators import validate_debts
from dn.llm.client import LLMClient
from dn.llm.schema_call import call_json


def _document_text(content: DocumentContent) -> str:
    return "\n".join(page.text for page in content.pages if page.text)


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def _debt_from_entry(entry: dict[str, Any], *, document_text: str) -> Debt:
    balance_raw = entry.get("balance")
    matched_in_source = bool(balance_raw) and balance_raw in document_text

    # 추출을 시도한 필드는 값의 성패와 무관하게 source=DOCUMENT 로 남긴다
    # (T06 세부 규칙). value 가 None 이면 결측은 결측대로 전파된다.
    return Debt(
        debt_id=str(uuid.uuid4()),
        creditor=Tracked(
            value=entry.get("creditor"), source=FieldSource.DOCUMENT, raw_text=entry.get("creditor")
        ),
        product_type=Tracked(
            value=normalize_product_type(entry.get("product_type")),
            source=FieldSource.DOCUMENT,
            raw_text=entry.get("product_type"),
        ),
        balance=Tracked(
            value=parse_money(balance_raw),
            source=FieldSource.DOCUMENT,
            raw_text=balance_raw if matched_in_source else None,
        ),
        executed_at=Tracked(
            value=_parse_date(entry.get("executed_at")),
            source=FieldSource.DOCUMENT,
            raw_text=entry.get("executed_at"),
        ),
        overdue_days=Tracked(value=entry.get("overdue_days"), source=FieldSource.DOCUMENT),
        is_secured=Tracked(value=entry.get("is_secured"), source=FieldSource.DOCUMENT),
    )


def extract(content: DocumentContent, *, client: LLMClient) -> list[Debt]:
    """`content` 에서 채무 목록을 추출한다."""
    document_text = _document_text(content)
    raw = call_json(
        client,
        system=EXTRACTION_SYSTEM_PROMPT,
        user=build_user_prompt(document_text),
        schema=EXTRACTION_SCHEMA,
    )

    debts = tuple(_debt_from_entry(entry, document_text=document_text) for entry in raw["debts"])
    return list(validate_debts(debts, doc_total_balance=None))
