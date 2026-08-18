"""FastAPI 앱 팩토리."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from dn.api import routes_analysis, routes_document, routes_session
from dn.domain.errors import DomainError, StateTransitionError
from dn.settings import get_settings
from dn.web import routes as web_routes


def create_app() -> FastAPI:
    """`Settings` 를 로드하고 라우터를 등록한 `FastAPI` 인스턴스를 만든다."""
    settings = get_settings()
    app = FastAPI(title=settings.config.meta.service_name)

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
