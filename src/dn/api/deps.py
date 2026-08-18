"""FastAPI 의존성 주입 헬퍼. 라우터에 비즈니스 로직을 넣지 않기 위한 얇은 계층."""

from __future__ import annotations

from functools import lru_cache

from fastapi import HTTPException

from dn.domain.models import SessionState
from dn.llm.client import LLMClient, get_llm_client
from dn.settings import Settings, get_settings
from dn.storage.session_store import InMemorySessionStore, SessionStore


@lru_cache(maxsize=1)
def get_session_store() -> SessionStore:
    """세션 저장소 싱글턴. 데모/개발 환경은 인메모리로 충분하다."""
    return InMemorySessionStore()


def get_llm_client_dep(settings: Settings | None = None) -> LLMClient:
    return get_llm_client(settings or get_settings())


def get_session_or_404(session_id: str, store: SessionStore) -> SessionState:
    """세션을 조회한다. 없으면 404."""
    state = store.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    return state
