"""Where uploaded and executed PDFs live on disk.

Paths are stored in the database relative to the storage root so the whole
storage directory can be moved or restored from a backup without rewriting
rows.
"""

from __future__ import annotations

from pathlib import Path

from app.config import get_settings

PDF_MAGIC = b"%PDF-"


def is_pdf(data: bytes) -> bool:
    """Check the file signature rather than trusting the declared type."""

    return data[:1024].lstrip()[: len(PDF_MAGIC)] == PDF_MAGIC


def absolute(relative_path: str | Path) -> Path:
    path = Path(relative_path)
    return path if path.is_absolute() else get_settings().storage_root / path


def relative(absolute_path: str | Path) -> str:
    path = Path(absolute_path)
    try:
        return str(path.relative_to(get_settings().storage_root))
    except ValueError:
        return str(path)


def safe_stem(filename: str) -> str:
    """A filesystem-safe version of an uploaded name, without directories."""

    stem = Path(filename).name
    keep = [c if (c.isalnum() or c in "-_. ") else "_" for c in stem]
    cleaned = "".join(keep).strip().strip(".") or "contract.pdf"
    return cleaned[:120]


def upload_path(contract_id: str) -> Path:
    return get_settings().uploads_dir / f"{contract_id}.pdf"


def executed_path(contract_id: str, original_filename: str) -> Path:
    stem = Path(safe_stem(original_filename)).stem
    return get_settings().executed_dir / f"{stem}_executed_{contract_id[:8]}.pdf"


def write_upload(contract_id: str, data: bytes) -> Path:
    settings = get_settings()
    settings.ensure_directories()
    destination = upload_path(contract_id)
    destination.write_bytes(data)
    return destination
