"""FastAPI application.

Bind to 127.0.0.1. Driver Social Security numbers are inside these files and
must not cross a network — see CLAUDE.md, non-negotiable 2.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.api import audit, auth, config_routes, contracts, signatures, templates
from app.api.auth import require_auth
from app.config import get_settings
from app.database import create_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("contract_desk")


class UnsafeExposure(RuntimeError):
    """Raised rather than serving driver data to a network with no login."""


def check_exposure() -> None:
    """Refuse to answer a network until someone can be asked who they are.

    Binding beyond loopback is exactly what makes the desk reachable from a
    phone or another machine, and the files it serves contain Social
    Security numbers. Rather than trust a note in a README, the app will
    not start.
    """

    settings = get_settings()
    if settings.is_loopback:
        return

    from app.database import get_session_factory
    from app.services.auth import any_user_exists

    with get_session_factory()() as session:
        if any_user_exists(session):
            return

    raise UnsafeExposure(
        f"Refusing to start on {settings.host}, which is reachable from the "
        "network, while no account exists. These files contain driver "
        "Social Security numbers.\n\n"
        "Create an account first:\n"
        "    python -m app.cli create-user\n\n"
        "Or leave HOST at 127.0.0.1 to keep the desk on this machine only."
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.ensure_directories()
    create_all()
    check_exposure()
    logger.info(
        "contract desk ready storage=%s host=%s",
        settings.storage_root,
        settings.host,
    )
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

    # Signing in is the one thing reachable without being signed in.
    app.include_router(auth.router, prefix="/api")

    # Everything else needs a session — unless no account exists at all,
    # which is the single-machine default. See app.services.auth.
    guarded = [Depends(require_auth)]
    app.include_router(contracts.router, prefix="/api", dependencies=guarded)
    app.include_router(config_routes.router, prefix="/api", dependencies=guarded)
    app.include_router(audit.router, prefix="/api", dependencies=guarded)
    app.include_router(templates.router, prefix="/api", dependencies=guarded)
    app.include_router(signatures.router, prefix="/api", dependencies=guarded)

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
