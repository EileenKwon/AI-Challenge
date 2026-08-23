"""FastAPI 앱 팩토리."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from dn.api import routes_analysis, routes_document, routes_session
from dn.api.deps import get_session_store
from dn.domain.errors import DomainError, StateTransitionError
from dn.settings import get_settings
from dn.storage.ttl import run_ttl_sweeper
from dn.web import routes as web_routes

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """TTL 스위퍼를 앱 수명주기에 배선한다.

    업로드 원본은 `upload_dir/{session_id}/` 에 저장되고, 화면(01_intro)과
    요약서 고지문은 "세션 종료 또는 TTL 만료 시 자동 삭제"를 약속한다.
    스위퍼가 기동되지 않으면 그 약속이 지켜지지 않으므로 반드시 여기서 띄운다.
    """
    settings = get_settings()
    store = get_session_store()
    task = asyncio.create_task(
        run_ttl_sweeper(
            store,
            ttl_minutes=settings.config.session.ttl_minutes,
            upload_dir=settings.upload_dir,
        )
    )
    logger.info(
        "ttl_sweeper_started",
        extra={"ttl_minutes": settings.config.session.ttl_minutes},
    )
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        logger.info("ttl_sweeper_stopped")


def create_app() -> FastAPI:
    """`Settings` 를 로드하고 라우터를 등록한 `FastAPI` 인스턴스를 만든다."""
    settings = get_settings()
    app = FastAPI(title=settings.config.meta.service_name, lifespan=_lifespan)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.exception_handler(StateTransitionError)
    async def state_transition_error_handler(
        request: Request, exc: StateTransitionError
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    app.include_router(routes_session.router)
    app.include_router(routes_document.router)
    app.include_router(routes_analysis.router)
    app.include_router(web_routes.landing_router)
    app.include_router(web_routes.router)

    return app


app = create_app()
