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
from dn.domain.models import Debt, ExtractionResult
from dn.domain.provenance import Tracked
from dn.ingest import jobs as upload_jobs
from dn.ingest.uploader import UploadValidationError, safe_filename, validate_upload
from dn.llm.client import LLMClient
from dn.pipeline.stages import transition
from dn.settings import get_settings
from dn.storage.session_store import SessionStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/session", tags=["document"])


@router.post("/{session_id}/document", status_code=202)
def upload_document(
    session_id: str,
    request: Request,
    file: UploadFile,
    store: SessionStore = Depends(get_session_store),
    client: LLMClient = Depends(get_llm_client_dep),
) -> dict:
    """PDF/이미지 업로드를 받아 파일 검증까지 동기로 끝내고, 이후(문서 읽기·
    PII 마스킹·AI 추출)는 백그라운드 작업으로 넘긴다.

    형식이 잘못된 파일(400)은 기다리게 하지 않고 즉시 알려준다. 느리고
    가변적인 부분(무료 LLM 티어의 rate limit 재시도로 3~14초+ 걸릴 수
    있음, 2026-09-06 실측)만 비동기로 돌려 진행상태 UI(`GET .../document/
    status`)를 붙일 수 있게 한다 — `report/jobs.py` 와 같은 이유·구조다.

    일부러 `async def` 가 아니라 동기 함수다 — 본문의 파일 검증·저장이
    블로킹 호출인데 `async def` 로 선언하면 Starlette 가 스레드풀로
    offload 하지 않고 단일 이벤트 루프에서 그대로 실행해 헬스체크를 막을
    수 있다(2026-09-06 실측 회귀). 동기 함수로 두면 스레드풀에서 실행된다.
    """
    get_session_or_404(session_id, store)
    settings = get_settings()
    if settings.config.ratelimit.enabled:
        ratelimit.check(
            ratelimit.client_key(request),
            limit=settings.config.ratelimit.llm_calls_per_ip,
            window_sec=settings.config.ratelimit.window_seconds,
        )

    content_bytes = file.file.read()
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

    job = upload_jobs.start_job(
        session_id, saved_path, canonical_mime, settings=settings, store=store, client=client
    )
    return {"job_id": job.job_id, **job.to_status_dict()}


@router.get("/{session_id}/document/status")
def get_document_status(session_id: str, job_id: str) -> dict:
    job = upload_jobs.get_job(job_id)
    if job is None or job.session_id != session_id:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return job.to_status_dict()


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
