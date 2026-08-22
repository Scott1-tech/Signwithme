"""Accounts, passwords and sessions.

The desk was built to run on one machine with no login, which is correct
while it only ever answers to that machine. The moment it is reachable from
anywhere else — a phone, another desk, a laptop at home — a login is the
thing standing between a driver's Social Security number and whoever finds
the address. So the two travel together: see the startup guard in
``app.main``, which refuses to bind to a network without an account.

Passwords are hashed with scrypt from the standard library. That avoids
adding a dependency to a compliance tool for something Python already does
well, and scrypt is deliberately expensive to attack in bulk.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import secrets
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.models import Session, User

# --- Password hashing -------------------------------------------------------

#: scrypt cost. 2**15 takes roughly a tenth of a second on office hardware,
#: which is unnoticeable on a login and painful to run millions of times.
SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1
SALT_BYTES = 16
KEY_BYTES = 32


def _maxmem(n: int, r: int, p: int) -> int:
    """OpenSSL caps scrypt memory at 32 MB unless told otherwise.

    The cost above needs about 33 MB, so without this every hash fails with
    "memory limit exceeded". Doubling the requirement leaves headroom for
    the parameters to be raised later without touching this again.
    """

    return 128 * n * r * p * 2

#: How long a signed-in browser stays signed in.
SESSION_DAYS = 14

#: The cookie the browser holds. Sessions live in the database; this is
#: only the key to one.
COOKIE_NAME = "contract_desk_session"

MIN_PASSWORD_LENGTH = 10


class PasswordTooShort(ValueError):
    pass


def hash_password(password: str) -> str:
    """``scrypt$n$r$p$salt$hash``, all hex."""

    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordTooShort(
            f"The password must be at least {MIN_PASSWORD_LENGTH} characters."
        )
    salt = secrets.token_bytes(SALT_BYTES)
    key = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=KEY_BYTES,
        maxmem=_maxmem(SCRYPT_N, SCRYPT_R, SCRYPT_P),
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${key.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    """Constant-time check. Never raises on a malformed hash."""

    try:
        scheme, n, r, p, salt_hex, key_hex = encoded.split("$")
        if scheme != "scrypt":
            return False
        candidate = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(bytes.fromhex(key_hex)),
            maxmem=_maxmem(int(n), int(r), int(p)),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, bytes.fromhex(key_hex))


# --- Accounts ---------------------------------------------------------------


def normalise_username(username: str) -> str:
    return username.strip().lower()


def get_user(session: DbSession, username: str) -> User | None:
    return session.scalar(
        select(User).where(User.username == normalise_username(username))
    )


def any_user_exists(session: DbSession) -> bool:
    return session.scalar(select(User.id).limit(1)) is not None


def create_user(
    session: DbSession,
    *,
    username: str,
    password: str,
    display_name: str = "",
) -> User:
    name = normalise_username(username)
    if not name:
        raise ValueError("A username is required.")
    if get_user(session, name) is not None:
        raise ValueError(f"There is already an account called “{name}”.")

    user = User(
        username=name,
        display_name=display_name.strip(),
        password_hash=hash_password(password),
    )
    session.add(user)
    session.flush()
    return user


def set_password(session: DbSession, user: User, password: str) -> None:
    user.password_hash = hash_password(password)
    # Every other browser is signed out: a password change should end the
    # sessions it was meant to protect against.
    for existing in session.scalars(
        select(Session).where(Session.user_id == user.id)
    ).all():
        session.delete(existing)
    session.flush()


# --- Sign-in throttling -----------------------------------------------------

#: Failures are counted in memory. The desk is one process on one machine,
#: so this is enough to make guessing slow without adding infrastructure.
_FAILURES: dict[str, list[dt.datetime]] = {}

MAX_ATTEMPTS = 8
LOCKOUT_WINDOW = dt.timedelta(minutes=15)


@dataclass
class Throttle:
    locked: bool
    remaining: int


def _recent_failures(key: str, now: dt.datetime) -> list[dt.datetime]:
    cutoff = now - LOCKOUT_WINDOW
    kept = [stamp for stamp in _FAILURES.get(key, []) if stamp > cutoff]
    if kept:
        _FAILURES[key] = kept
    else:
        _FAILURES.pop(key, None)
    return kept


def check_throttle(key: str, now: dt.datetime | None = None) -> Throttle:
    moment = now or dt.datetime.now(dt.timezone.utc)
    failures = _recent_failures(key.lower(), moment)
    return Throttle(
        locked=len(failures) >= MAX_ATTEMPTS,
        remaining=max(0, MAX_ATTEMPTS - len(failures)),
    )


def record_failure(key: str, now: dt.datetime | None = None) -> None:
    moment = now or dt.datetime.now(dt.timezone.utc)
    _FAILURES.setdefault(key.lower(), []).append(moment)


def clear_failures(key: str) -> None:
    _FAILURES.pop(key.lower(), None)


def reset_throttle() -> None:
    """Used by the tests, so one case cannot lock out the next."""

    _FAILURES.clear()


# --- Sessions ---------------------------------------------------------------


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def start_session(
    session: DbSession, user: User, *, ip_address: str | None = None
) -> str:
    """Create a session and return the cookie value, which is never stored."""

    token = secrets.token_urlsafe(32)
    now = dt.datetime.now(dt.timezone.utc)
    session.add(
        Session(
            token_hash=_hash_token(token),
            user_id=user.id,
            created_at=now,
            expires_at=now + dt.timedelta(days=SESSION_DAYS),
            ip_address=ip_address,
        )
    )
    user.last_login_at = now
    session.flush()
    return token


def user_for_token(session: DbSession, token: str | None) -> User | None:
    if not token:
        return None

    row = session.scalar(
        select(Session).where(Session.token_hash == _hash_token(token))
    )
    if row is None:
        return None

    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=dt.timezone.utc)
    if expires <= dt.datetime.now(dt.timezone.utc):
        session.delete(row)
        session.flush()
        return None

    if row.user is None or not row.user.is_active:
        return None
    return row.user


def end_session(session: DbSession, token: str | None) -> None:
    if not token:
        return
    row = session.scalar(
        select(Session).where(Session.token_hash == _hash_token(token))
    )
    if row is not None:
        session.delete(row)
        session.flush()


def purge_expired(session: DbSession) -> int:
    now = dt.datetime.now(dt.timezone.utc)
    stale = session.scalars(select(Session)).all()
    removed = 0
    for row in stale:
        expires = row.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=dt.timezone.utc)
        if expires <= now:
            session.delete(row)
            removed += 1
    if removed:
        session.flush()
    return removed
