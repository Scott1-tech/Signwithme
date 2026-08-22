"""Signing in.

Accounts are opt-in. With none created the desk behaves exactly as it did
before — no login, one machine, nothing to remember — because that is the
right shape for a tool that only answers to the computer it runs on.

Create an account and every route needs a session. That is also the switch
that lets the app be reached from anywhere else: ``app.main`` refuses to
bind to a network until an account exists.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.database import get_db
from app.models import User
from app.services import auth as auth_service

logger = logging.getLogger("contract_desk.auth")

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    username: str
    display_name: str
    label: str


class AuthStatus(BaseModel):
    #: False while no account exists, which is the single-machine default.
    login_required: bool
    signed_in: bool
    user: UserOut | None = None


def _as_out(user: User) -> UserOut:
    return UserOut(
        username=user.username,
        display_name=user.display_name,
        label=user.label,
    )


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


# --------------------------------------------------------------------------
# The guard every other router hangs off
# --------------------------------------------------------------------------


def require_auth(
    session: DbSession = Depends(get_db),
    contract_desk_session: str | None = Cookie(default=None),
) -> User | None:
    """The signed-in user, or None while the desk has no accounts.

    Raises 401 when accounts exist and this request has no live session.
    FastAPI caches dependencies per request, so a route that also wants the
    user does not pay for a second lookup.
    """

    if not auth_service.any_user_exists(session):
        return None

    user = auth_service.user_for_token(session, contract_desk_session)
    if user is None:
        raise HTTPException(status_code=401, detail="Please sign in.")
    return user


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------


@router.get("/status", response_model=AuthStatus)
def status(
    session: DbSession = Depends(get_db),
    contract_desk_session: str | None = Cookie(default=None),
) -> AuthStatus:
    """Whether a login is needed here, and whether this browser has one."""

    if not auth_service.any_user_exists(session):
        return AuthStatus(login_required=False, signed_in=False)

    user = auth_service.user_for_token(session, contract_desk_session)
    return AuthStatus(
        login_required=True,
        signed_in=user is not None,
        user=_as_out(user) if user else None,
    )


@router.post("/login", response_model=AuthStatus)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: DbSession = Depends(get_db),
) -> AuthStatus:
    username = auth_service.normalise_username(body.username)

    throttle = auth_service.check_throttle(username)
    if throttle.locked:
        # Deliberately vague about which account: this is also the answer a
        # stranger gets while guessing.
        raise HTTPException(
            status_code=429,
            detail="Too many failed attempts. Wait fifteen minutes and try "
            "again.",
        )

    user = auth_service.get_user(session, username)
    ok = user is not None and user.is_active and auth_service.verify_password(
        body.password, user.password_hash
    )

    if not ok or user is None:
        auth_service.record_failure(username)
        logger.warning("failed sign-in username=%s", username)
        # One message for a wrong name and a wrong password, so the form
        # cannot be used to find out which accounts exist.
        raise HTTPException(
            status_code=401, detail="That username and password do not match."
        )

    auth_service.clear_failures(username)
    token = auth_service.start_session(session, user, ip_address=_client_ip(request))

    settings = get_settings()
    response.set_cookie(
        key=auth_service.COOKIE_NAME,
        value=token,
        max_age=auth_service.SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        samesite="lax",
        # Off by default: on a private network the desk is served over plain
        # HTTP. Turn it on behind HTTPS.
        secure=settings.session_cookie_secure,
        path="/",
    )
    logger.info("signed in username=%s", user.username)

    return AuthStatus(login_required=True, signed_in=True, user=_as_out(user))


@router.post("/logout", response_model=AuthStatus)
def logout(
    response: Response,
    session: DbSession = Depends(get_db),
    contract_desk_session: str | None = Cookie(default=None),
) -> AuthStatus:
    auth_service.end_session(session, contract_desk_session)
    response.delete_cookie(auth_service.COOKIE_NAME, path="/")
    return AuthStatus(
        login_required=auth_service.any_user_exists(session), signed_in=False
    )


@router.get("/me", response_model=UserOut)
def me(user: User | None = Depends(require_auth)) -> UserOut:
    if user is None:
        raise HTTPException(
            status_code=404, detail="This desk has no accounts; no one is signed in."
        )
    return _as_out(user)
