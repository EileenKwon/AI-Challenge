"""세션 생성·동의·삭제 라우터. 비즈니스 로직은 여기 두지 않는다."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from dn.api.deps import get_session_or_404, get_session_store
from dn.domain.enums import SessionStage
from dn.domain.models import SessionState
from dn.pipeline.stages import transition
from dn.storage.session_store import SessionStore

router = APIRouter(prefix="/api/session", tags=["session"])


class SessionResponse(BaseModel):
    session_id: str
    stage: str


@router.post("", response_model=SessionResponse, status_code=201)
def create_session(store: SessionStore = Depends(get_session_store)) -> SessionResponse:
    now = datetime.now()
    state = SessionState(session_id=str(uuid.uuid4()), created_at=now, updated_at=now)
    store.create(state)
    return SessionResponse(session_id=state.session_id, stage=state.stage.value)


@router.post("/{session_id}/consent", response_model=SessionResponse)
def give_consent(
    session_id: str, store: SessionStore = Depends(get_session_store)
) -> SessionResponse:
    state = get_session_or_404(session_id, store)
    new_state = transition(state, SessionStage.S1_UPLOADED)
    new_state = new_state.model_copy(
        update={"consent_at": datetime.now(), "updated_at": datetime.now()}
    )
    store.save(new_state)
    return SessionResponse(session_id=new_state.session_id, stage=new_state.stage.value)


@router.delete("/{session_id}", status_code=204)
def delete_session(session_id: str, store: SessionStore = Depends(get_session_store)) -> None:
    get_session_or_404(session_id, store)
    store.delete(session_id)
