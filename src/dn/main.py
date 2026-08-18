"""FastAPI 앱 팩토리."""

from __future__ import annotations

from fastapi import FastAPI

from dn.settings import get_settings


def create_app() -> FastAPI:
    """`Settings` 를 로드하고 라우터를 등록한 `FastAPI` 인스턴스를 만든다."""
    settings = get_settings()
    app = FastAPI(title=settings.config.meta.service_name)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
