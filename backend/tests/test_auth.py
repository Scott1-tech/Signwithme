"""Accounts, sessions, and the guard that keeps driver data off a network."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.database import get_session_factory, reset_engine
from app.services import auth
from tests.conftest import build_flattened_contract


@pytest.fixture(autouse=True)
def clean_throttle() -> Iterator[None]:
    auth.reset_throttle()
    yield
    auth.reset_throttle()


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("SSN_SALT", "salt-for-tests")
    get_settings.cache_clear()
    reset_engine()

    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client

    get_settings.cache_clear()
    reset_engine()


def add_account(username: str = "dana", password: str = "correct-horse-battery") -> None:
    with get_session_factory()() as session:
        auth.create_user(
            session, username=username, password=password, display_name="Dana Okafor"
        )
        session.commit()


def sign_in(client: TestClient, username="dana", password="correct-horse-battery"):
    return client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )


# --------------------------------------------------------------------------
# Passwords
# --------------------------------------------------------------------------


def test_a_password_round_trips() -> None:
    encoded = auth.hash_password("correct-horse-battery")
    assert auth.verify_password("correct-horse-battery", encoded) is True
    assert auth.verify_password("wrong-horse-battery", encoded) is False


def test_the_password_is_not_recoverable_from_the_hash() -> None:
    encoded = auth.hash_password("correct-horse-battery")
    assert "correct-horse-battery" not in encoded
    assert encoded.startswith("scrypt$")


def test_the_same_password_hashes_differently_each_time() -> None:
    """A per-password salt, so one crack does not reveal the rest."""

    assert auth.hash_password("correct-horse-battery") != auth.hash_password(
        "correct-horse-battery"
    )


def test_a_short_password_is_refused() -> None:
    with pytest.raises(auth.PasswordTooShort):
        auth.hash_password("short")


@pytest.mark.parametrize("junk", ["", "not-a-hash", "scrypt$bad", "md5$1$2$3$4$5"])
def test_a_malformed_hash_never_verifies(junk: str) -> None:
    assert auth.verify_password("anything", junk) is False


# --------------------------------------------------------------------------
# With no accounts, the desk works as it always did
# --------------------------------------------------------------------------


def test_without_accounts_no_login_is_required(client: TestClient) -> None:
    assert client.get("/api/contracts").status_code == 200
    assert client.get("/api/auth/status").json() == {
        "login_required": False,
        "signed_in": False,
        "user": None,
    }


def test_creating_the_first_account_turns_the_login_on(client: TestClient) -> None:
    assert client.get("/api/contracts").status_code == 200

    add_account()

    assert client.get("/api/contracts").status_code == 401
    assert client.get("/api/auth/status").json()["login_required"] is True


# --------------------------------------------------------------------------
# Signing in
# --------------------------------------------------------------------------


def test_signing_in_and_out(client: TestClient) -> None:
    add_account()

    response = sign_in(client)
    assert response.status_code == 200
    assert response.json()["user"]["label"] == "Dana Okafor"

    assert client.get("/api/contracts").status_code == 200

    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/contracts").status_code == 401


def test_the_wrong_password_is_refused(client: TestClient) -> None:
    add_account()
    response = sign_in(client, password="not-the-password")

    assert response.status_code == 401
    assert client.get("/api/contracts").status_code == 401


def test_an_unknown_account_gets_the_same_message_as_a_wrong_password(
    client: TestClient,
) -> None:
    """Otherwise the form tells a stranger which accounts exist."""

    add_account()
    unknown = sign_in(client, username="nobody", password="whatever-long-enough")
    wrong = sign_in(client, password="not-the-password")

    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


def test_the_session_cookie_is_not_readable_by_scripts(client: TestClient) -> None:
    add_account()
    response = sign_in(client)
    cookie = response.headers["set-cookie"].lower()

    assert "httponly" in cookie
    assert "samesite=lax" in cookie


def test_the_cookie_value_is_not_stored_in_the_database(
    client: TestClient, tmp_path: Path
) -> None:
    """A copy of the database must not hand over live sessions."""

    add_account()
    sign_in(client)
    token = client.cookies.get(auth.COOKIE_NAME)

    assert token
    assert token.encode() not in (tmp_path / "test.db").read_bytes()


def test_a_made_up_cookie_does_not_work(client: TestClient) -> None:
    add_account()
    client.cookies.set(auth.COOKIE_NAME, "pretend-token")
    assert client.get("/api/contracts").status_code == 401


def test_repeated_failures_are_throttled(client: TestClient) -> None:
    add_account()
    for _ in range(auth.MAX_ATTEMPTS):
        sign_in(client, password="wrong-password-here")

    blocked = sign_in(client, password="wrong-password-here")
    assert blocked.status_code == 429

    # Even the right password waits, which is the point.
    assert sign_in(client).status_code == 429


def test_a_successful_sign_in_clears_the_count(client: TestClient) -> None:
    add_account()
    for _ in range(auth.MAX_ATTEMPTS - 1):
        sign_in(client, password="wrong-password-here")

    assert sign_in(client).status_code == 200
    assert auth.check_throttle("dana").remaining == auth.MAX_ATTEMPTS


def test_an_expired_session_stops_working(client: TestClient) -> None:
    add_account()
    sign_in(client)
    assert client.get("/api/contracts").status_code == 200

    from app.models import Session as SessionRow

    with get_session_factory()() as session:
        row = session.scalars(__import__("sqlalchemy").select(SessionRow)).one()
        row.expires_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)
        session.commit()

    assert client.get("/api/contracts").status_code == 401


def test_changing_a_password_signs_the_browser_out(client: TestClient) -> None:
    add_account()
    sign_in(client)
    assert client.get("/api/contracts").status_code == 200

    with get_session_factory()() as session:
        user = auth.get_user(session, "dana")
        auth.set_password(session, user, "a-brand-new-password")
        session.commit()

    assert client.get("/api/contracts").status_code == 401


# --------------------------------------------------------------------------
# Every route is behind the guard
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/api/contracts",
        "/api/templates",
        "/api/signatures",
        "/api/audit",
        "/api/audit/export",
        "/api/config/fields",
        "/api/config/carrier",
    ],
)
def test_every_listing_route_needs_a_session(client: TestClient, path: str) -> None:
    add_account()
    assert client.get(path).status_code == 401


def test_uploading_a_contract_needs_a_session(
    client: TestClient, tmp_path: Path
) -> None:
    add_account()
    pdf = build_flattened_contract(tmp_path / "contract.pdf")

    with open(pdf, "rb") as handle:
        response = client.post(
            "/api/contracts",
            files={"file": ("contract.pdf", handle, "application/pdf")},
        )

    assert response.status_code == 401


def test_health_stays_open(client: TestClient) -> None:
    """Uptime checks must not need a password."""

    add_account()
    assert client.get("/api/health").json() == {"status": "ok"}


# --------------------------------------------------------------------------
# The approval record
# --------------------------------------------------------------------------


def test_the_approval_records_the_account_beside_the_typed_name(
    client: TestClient, tmp_path: Path
) -> None:
    add_account()
    sign_in(client)

    pdf = build_flattened_contract(tmp_path / "contract.pdf")
    with open(pdf, "rb") as handle:
        contract = client.post(
            "/api/contracts",
            files={"file": ("contract.pdf", handle, "application/pdf")},
        ).json()

    approved = client.post(
        f"/api/contracts/{contract['id']}/approve",
        json={"approved_by": "Dana Okafor", "acknowledge_errors": False},
    ).json()

    # The typed name is what was attested to; the account is context.
    assert approved["approval"]["approved_by"] == "Dana Okafor"
    assert approved["approval"]["signed_in_as"] == "dana"


def test_the_typed_name_is_still_required_when_signed_in(
    client: TestClient, tmp_path: Path
) -> None:
    """Being logged in is not the same as attesting. Do not conflate them."""

    add_account()
    sign_in(client)

    pdf = build_flattened_contract(tmp_path / "contract.pdf")
    with open(pdf, "rb") as handle:
        contract = client.post(
            "/api/contracts",
            files={"file": ("contract.pdf", handle, "application/pdf")},
        ).json()

    response = client.post(
        f"/api/contracts/{contract['id']}/approve",
        json={"approved_by": "   ", "acknowledge_errors": False},
    )
    assert response.status_code == 400


# --------------------------------------------------------------------------
# The exposure guard
# --------------------------------------------------------------------------


def test_the_app_refuses_to_face_the_network_without_an_account(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'exposed.db'}")
    monkeypatch.setenv("SSN_SALT", "salt-for-tests")
    monkeypatch.setenv("HOST", "0.0.0.0")
    get_settings.cache_clear()
    reset_engine()

    from app.main import UnsafeExposure, create_app

    with pytest.raises(UnsafeExposure, match="Social Security"):
        with TestClient(create_app()):
            pass

    get_settings.cache_clear()
    reset_engine()


def test_the_app_starts_on_the_network_once_an_account_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'exposed.db'}")
    monkeypatch.setenv("SSN_SALT", "salt-for-tests")
    monkeypatch.setenv("HOST", "0.0.0.0")
    get_settings.cache_clear()
    reset_engine()

    from app.database import create_all

    create_all()
    add_account()

    from app.main import create_app

    with TestClient(create_app()) as test_client:
        assert test_client.get("/api/contracts").status_code == 401

    get_settings.cache_clear()
    reset_engine()


def test_loopback_never_needs_an_account(client: TestClient) -> None:
    """The single-machine default must keep working untouched."""

    assert get_settings().is_loopback is True
    assert client.get("/api/contracts").status_code == 200
