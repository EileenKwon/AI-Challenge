"""문서 업로드 · 추출 확인 라우터.

업로드 → ingest → mask → scan → extract → S2 전이 (ARCHITECTURE.md §8).
비즈니스 로직은 각 모듈에 있고, 라우터는 호출과 상태 저장만 한다.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel

from dn.api.deps import get_llm_client_dep, get_session_or_404, get_session_store
from dn.domain.enums import SessionStage
from dn.domain.errors import DomainError
from dn.domain.models import ExtractionResult
from dn.extraction.extractor import extract
from dn.ingest import pdf_reader
from dn.ingest.injection_scanner import apply as apply_scan
from dn.ingest.injection_scanner import scan as scan_injection
from dn.ingest.pii_masker import mask as mask_pii
from dn.ingest.uploader import UploadValidationError, safe_filename, validate_upload
from dn.llm.client import LLMClient
from dn.pipeline.stages import transition
from dn.settings import get_settings
from dn.storage.session_store import SessionStore

router = APIRouter(prefix="/api/session", tags=["document"])


@router.post("/{session_id}/document")
async def upload_document(
    session_id: str,
    file: UploadFile,
    store: SessionStore = Depends(get_session_store),
    client: LLMClient = Depends(get_llm_client_dep),
) -> dict:
    state = get_session_or_404(session_id, store)
    settings = get_settings()

    content_bytes = await file.read()
    try:
        validate_upload(
            filename=file.filename or "upload",
            content_type=file.content_type or "application/octet-stream",
            size_bytes=len(content_bytes),
            settings=settings,
        )
    except UploadValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    session_dir = settings.upload_dir / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    saved_path = session_dir / safe_filename(file.filename or "upload.pdf")
    saved_path.write_bytes(content_bytes)

    try:
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

    debts = extract(document, client=client)
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
