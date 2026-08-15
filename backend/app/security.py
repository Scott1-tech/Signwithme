"""Hashing and masking.

The Social Security number is the reason this app runs on one laptop. It is
never written to the database: only the last four digits, for identification,
and a salted SHA-256 hash, so a re-upload of the same driver can be matched
without holding the number. The full value stays inside the PDF on disk.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.config import get_settings

_CHUNK = 1024 * 1024


def digits_only(value: str | None) -> str:
    return "".join(character for character in (value or "") if character.isdigit())


def ssn_last4(value: str | None) -> str | None:
    number = digits_only(value)
    return number[-4:] if len(number) >= 4 else None


def hash_ssn(value: str | None, salt: str | None = None) -> str | None:
    """Salted SHA-256 of the digits, or None when there is nothing to hash."""

    number = digits_only(value)
    if not number:
        return None
    pepper = salt if salt is not None else get_settings().ssn_salt
    return hashlib.sha256(f"{pepper}:{number}".encode("utf-8")).hexdigest()


def mask_ssn(value: str | None) -> str | None:
    """``***-**-6789``. The only form of an SSN the API ever returns."""

    last = ssn_last4(value)
    return f"***-**-{last}" if last else None


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()
