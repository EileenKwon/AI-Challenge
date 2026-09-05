"""문서 업로드 · 추출 확인 라우터.

업로드 → ingest → mask → scan → extract → S2 전이 (ARCHITECTURE.md §8).
비즈니스 로직은 각 모듈에 있고, 라우터는 호출과 상태 저장만 한다.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from pydantic import BaseModel

from dn.api import ratelimit
from dn.api.deps import get_llm_client_dep, get_session_or_404, get_session_store
from dn.domain.enums import FieldSource, ProductType, SessionStage
from dn.domain.errors import DomainError
from dn.domain.models import Debt, ExtractionResult
from dn.domain.provenance import Tracked
from dn.extraction.extractor import extract
from dn.ingest import image_reader, pdf_reader
from dn.ingest.injection_scanner import apply as apply_scan
from dn.ingest.injection_scanner import scan as scan_injection
from dn.ingest.pii_masker import mask as mask_pii
from dn.ingest.uploader import (
    UploadValidationError,
    file_kind_for,
    safe_filename,
    validate_upload,
)
from dn.llm.client import LLMClient
from dn.pipeline.stages import transition
from dn.settings import get_settings
from dn.storage.session_store import SessionStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/session", tags=["document"])


@router.post("/{session_id}/document")
async def upload_document(
    session_id: str,
    request: Request,
    file: UploadFile,
    store: SessionStore = Depends(get_session_store),
    client: LLMClient = Depends(get_llm_client_dep),
) -> dict:
    state = get_session_or_404(session_id, store)
    settings = get_settings()
    if settings.config.ratelimit.enabled:
        ratelimit.check(
            ratelimit.client_key(request),
            limit=settings.config.ratelimit.llm_calls_per_ip,
            window_sec=settings.config.ratelimit.window_seconds,
        )

    content_bytes = await file.read()
    try:
        canonical_mime = validate_upload(
            filename=file.filename or "upload",
            content_type=file.content_type or "application/octet-stream",
            size_bytes=len(content_bytes),
            content=content_bytes,
            settings=settings,
        )
    except UploadValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    session_dir = settings.upload_dir / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    saved_path = session_dir / safe_filename(file.filename or "upload.pdf")
    saved_path.write_bytes(content_bytes)

    # 검증 단계에서 이미 확정한 정규 MIME 으로 처리기를 나눈다. pypdf 를
    # PDF 가 아닌 파일에 호출하지 않기 위해서다 — PNG/JPEG 를 PDF 판독기에
    # 넘기면 "PDF 를 열 수 없습니다" 크래시가 난다(2026-09-06 버그 리포트).
    try:
        if file_kind_for(canonical_mime) == "image":
            document = image_reader.read(saved_path, doc_id=saved_path.name)
        else:
            document = pdf_reader.read(saved_path, doc_id=saved_path.name, settings=settings)
    except DomainError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    cleaned_pages = []
    for page in document.pages:
        if page.text is None:
            cleaned_pages.append(page)
            continue
        scan_report = scan_injection(page.text, settings=settings)
        cleaned_text = apply_scan(page.text, scan_report)
        masked_text, _ = mask_pii(cleaned_text)
        cleaned_pages.append(page.model_copy(update={"text": masked_text}))
    document = document.model_copy(update={"pages": tuple(cleaned_pages)})

    try:
        debts = extract(document, client=client)
    except Exception as exc:
        # LLM 백엔드 장애·한도 초과로 추출이 막혀도 서비스 전체가 죽으면 안 된다.
        # 세션은 S1 에 그대로 두고 503 으로 돌려주면, 화면 02 의 기존 오류 표시가
        # 이 문구를 그대로 띄우고 사용자는 다른 입력 방식으로 넘어갈 수 있다.
        logger.warning("extraction_failed", extra={"error": type(exc).__name__})
        raise HTTPException(
            status_code=503,
            detail=(
                "AI 문서 추출을 일시적으로 사용할 수 없습니다. "
                '아래 "문서 없이 직접 입력"으로 진행해 주세요.'
            ),
        ) from exc
    extraction = ExtractionResult(debts=tuple(debts))

    new_state = transition(state, SessionStage.S2_EXTRACTED)
    new_state = new_state.model_copy(
        update={"document": document, "extraction": extraction, "updated_at": datetime.now()}
    )
    store.save(new_state)
    return {
        "session_id": new_state.session_id,
        "stage": new_state.stage.value,
        "debt_count": len(debts),
    }


class ManualDebtEntry(BaseModel):
    """화면 02 "문서 없이 직접 입력" 의 채무 1건."""

    creditor: str
    product_type: ProductType | None = None
    balance: Decimal | None = None
    executed_at: date | None = None
    overdue_days: int | None = None
    is_secured: bool | None = None


class ManualDebtsRequest(BaseModel):
    debts: list[ManualDebtEntry]


def _debt_from_manual_entry(entry: ManualDebtEntry) -> Debt:
    """직접 입력값을 `Debt` 로 옮긴다. 빈 칸은 UNKNOWN 으로 남긴다.

    `confidence` 는 채우지 않는다 — 문서 추출값의 신뢰도를 뜻하는 필드이고
    (`Tracked` 정의 참고), 사용자가 직접 적은 값에 추출 신뢰도를 붙이면
    화면 03 이 근거 없는 저신뢰 경고를 띄운다.
    """

    def tracked(value: object) -> Tracked:
        if value is None:
            return Tracked()
        return Tracked(value=value, source=FieldSource.USER_INPUT)

    return Debt(
        debt_id=str(uuid.uuid4()),
        creditor=tracked(entry.creditor),
        product_type=tracked(entry.product_type),
        balance=tracked(entry.balance),
        executed_at=tracked(entry.executed_at),
        overdue_days=tracked(entry.overdue_days),
        is_secured=tracked(entry.is_secured),
    )


@router.post("/{session_id}/manual-debts")
def enter_debts_manually(
    session_id: str,
    body: ManualDebtsRequest,
    store: SessionStore = Depends(get_session_store),
) -> dict:
    """조회서 없이 채무를 직접 입력한다 (기획서 화면 02 의 네 번째 방식).

    문서 경로와 같은 `S2_EXTRACTED` 로 도착시킨다 — 이후 화면 03~07 이
    입력 방식을 구분하지 않고 그대로 동작하게 하기 위해서다. 출처는 전부
    `USER_INPUT` 이라 설명가능성 번들과 화면 배지에 "입력" 으로 드러난다.
    """
    state = get_session_or_404(session_id, store)
    settings = get_settings()

    entries = [e for e in body.debts if e.creditor.strip()]
    if not entries:
        raise HTTPException(status_code=400, detail="채무를 최소 1건 입력해야 합니다.")
    max_debts = settings.config.extraction.max_debts
    if len(entries) > max_debts:
        raise HTTPException(
            status_code=400, detail=f"채무는 최대 {max_debts}건까지 입력할 수 있습니다."
        )

    extraction = ExtractionResult(debts=tuple(_debt_from_manual_entry(e) for e in entries))
    new_state = transition(state, SessionStage.S2_EXTRACTED)
    new_state = new_state.model_copy(
        update={"extraction": extraction, "updated_at": datetime.now()}
    )
    store.save(new_state)
    return {
        "session_id": new_state.session_id,
        "stage": new_state.stage.value,
        "debt_count": len(entries),
    }


@router.get("/{session_id}/extraction")
def get_extraction(
    session_id: str, store: SessionStore = Depends(get_session_store)
) -> ExtractionResult:
    state = get_session_or_404(session_id, store)
    return state.extraction or ExtractionResult()


class FieldConfirmation(BaseModel):
    debt_index: int
    field_name: str
    user_confirmed: bool = True


@router.patch("/{session_id}/extraction")
def patch_extraction(
    session_id: str,
    confirmations: list[FieldConfirmation],
    store: SessionStore = Depends(get_session_store),
) -> ExtractionResult:
    """필드별 확인 상태만 갱신한다. 값 수정은 이후 반복에서 다룬다."""
    state = get_session_or_404(session_id, store)
    extraction = state.extraction or ExtractionResult()
    debts = list(extraction.debts)

    for c in confirmations:
        if c.debt_index >= len(debts):
            continue
        debt = debts[c.debt_index]
        tracked = getattr(debt, c.field_name, None)
        if tracked is None:
            continue
        updated_tracked = tracked.model_copy(update={"user_confirmed": c.user_confirmed})
        debts[c.debt_index] = debt.model_copy(update={c.field_name: updated_tracked})

    new_extraction = extraction.model_copy(update={"debts": tuple(debts)})
    new_state = state.model_copy(
        update={"extraction": new_extraction, "updated_at": datetime.now()}
    )
    store.save(new_state)
    return new_extraction


@router.post("/{session_id}/confirm")
def confirm_extraction(session_id: str, store: SessionStore = Depends(get_session_store)) -> dict:
    state = get_session_or_404(session_id, store)
    new_state = transition(state, SessionStage.S3_CONFIRMED)
    new_state = new_state.model_copy(update={"updated_at": datetime.now()})
    store.save(new_state)
    return {"session_id": new_state.session_id, "stage": new_state.stage.value}
