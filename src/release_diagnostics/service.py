from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import uvicorn
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .infrai_client import InfraiClient, InfraiError


class FailedBuild(BaseModel):
    build_id: str = Field(min_length=1)
    service: str = Field(min_length=1)
    commit_sha: str = Field(min_length=7)
    exception: str = Field(min_length=1)


class CapturedBuild(BaseModel):
    event_id: str
    error_group_id: str
    release_action: str


class ReleaseDiagnostic(BaseModel):
    error_group_id: str
    is_resolved: bool
    count: int
    representative_event: dict[str, Any] | None = None


def create_app(client: InfraiClient | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if client is not None:
            client.close()

    app = FastAPI(title="Build release diagnostics", lifespan=lifespan)

    def get_client(request: Request) -> InfraiClient:
        supplied = getattr(request.app.state, "infrai_client", None)
        if supplied is not None:
            return supplied
        created = InfraiClient()
        request.app.state.infrai_client = created
        return created

    @app.exception_handler(InfraiError)
    async def infrai_error_handler(_: Request, exc: InfraiError) -> JSONResponse:
        status = exc.status_code if 400 <= exc.status_code < 500 else 502
        return JSONResponse(
            status_code=status,
            content={"detail": {"code": exc.code, "error": exc.detail}},
        )

    @app.post("/build-events/failed", response_model=CapturedBuild)
    def capture_failed_build(
        build: FailedBuild,
        infrai: InfraiClient = Depends(get_client),
    ) -> CapturedBuild:
        captured = infrai.capture_build_error(**build.model_dump())
        return CapturedBuild(
            event_id=str(captured["event_id"]),
            error_group_id=str(captured["error_group_id"]),
            release_action="hold",
        )

    @app.get("/release-diagnostics/{error_group_id}", response_model=ReleaseDiagnostic)
    def read_release_diagnostic(
        error_group_id: str,
        infrai: InfraiClient = Depends(get_client),
    ) -> ReleaseDiagnostic:
        group = infrai.get_group_detail(error_group_id)
        return ReleaseDiagnostic(
            error_group_id=error_group_id,
            is_resolved=bool(group["is_resolved"]),
            count=int(group["count"]),
            representative_event=group.get("representative_event"),
        )

    if client is not None:
        app.state.infrai_client = client
    return app


app = create_app()


def run() -> None:
    uvicorn.run("release_diagnostics.service:app", host="127.0.0.1", port=8000)
