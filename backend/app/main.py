"""FastAPI application.

Bind to 127.0.0.1. Driver Social Security numbers are inside these files and
must not cross a network — see CLAUDE.md, non-negotiable 2.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.api import audit, config_routes, contracts
from app.config import get_settings
from app.database import create_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("contract_desk")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.ensure_directories()
    create_all()
    logger.info("contract desk ready storage=%s", settings.storage_root)
    yield


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Driver Contract Review Desk",
        version="1.0.0",
        summary="Local-only review and execution of signed driver contracts.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Preview-Page", "X-Placement-Count", "X-Placement-Pages"],
    )

    app.include_router(contracts.router, prefix="/api")
    app.include_router(config_routes.router, prefix="/api")
    app.include_router(audit.router, prefix="/api")

    @app.get("/api/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # HEAD as well as GET: platform health probes and uptime checkers send
    # HEAD /, and FastAPI — unlike plain Starlette — does not add it for you.
    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    def root() -> RedirectResponse:
        """Send the root to the API docs.

        Every route lives under /api, so a bare / used to be a bare 404 —
        which reads as "the deployment is broken" when it is actually
        working. The reviewer's interface is the separate frontend app;
        anyone landing here wants the API.
        """

        return RedirectResponse(url="/docs")

    return app


app = create_app()
