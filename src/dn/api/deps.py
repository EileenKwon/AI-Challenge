"""FastAPI 의존성 주입 헬퍼. 라우터에 비즈니스 로직을 넣지 않기 위한 얇은 계층."""

from __future__ import annotations

from functools import lru_cache

from fastapi import HTTPException

from dn.domain.models import SessionState
from dn.llm.client import LLMClient, get_llm_client
from dn.settings import Settings, get_settings
from dn.storage.session_store import SessionStore, SqliteSessionStore


@lru_cache(maxsize=1)
def get_session_store() -> SessionStore:
    """세션 저장소 싱글턴. `DN_SESSION_DB` 경로에 SQLite로 영속화한다.

    프로세스 재시작(배포 환경의 재배포·재시작 포함)에도 세션이 살아남아야 하므로
    인메모리 구현은 쓰지 않는다 — 테스트에서만 `InMemorySessionStore` 를 직접 쓴다.
    """
    return SqliteSessionStore(get_settings().session_db_path)


def get_llm_client_dep(settings: Settings | None = None) -> LLMClient:
    return get_llm_client(settings or get_settings())


def get_session_or_404(session_id: str, store: SessionStore) -> SessionState:
    """세션을 조회한다. 없으면 404."""
    state = store.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    return state
