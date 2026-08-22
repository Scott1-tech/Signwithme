"""Append-only audit writer.

Every approval lands in two places: the ``approvals`` table, which the
audit screen reads, and a JSON-lines file that is only ever appended to. The
file is the belt-and-braces copy an auditor can read without the app, and it
survives a database that has been restored, moved, or rebuilt.

Nothing here logs a field value. Field keys, rule ids, page numbers, and the
approver's name only.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Sequence

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Approval, Contract

logger = logging.getLogger("contract_desk.audit")

AUDIT_FILENAME = "audit.jsonl"


def audit_log_path() -> Path:
    return get_settings().storage_root / AUDIT_FILENAME


def _append_line(payload: dict) -> None:
    path = audit_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def record_approval(
    session: Session,
    contract: Contract,
    *,
    approved_by: str,
    error_count: int,
    overridden: bool,
    pages_stamped: Sequence[int],
    signature_hash: str | None,
    ip_address: str | None,
    signed_in_as: str | None = None,
) -> Approval:
    """Write the approval record. Never updated, never deleted."""

    approval = Approval(
        contract_id=contract.id,
        approved_by=approved_by.strip(),
        approved_at=dt.datetime.now(dt.timezone.utc),
        error_count_at_approval=error_count,
        overridden=overridden,
        pages_stamped=list(pages_stamped),
        signature_hash=signature_hash,
        ip_address=ip_address,
        signed_in_as=signed_in_as,
    )
    session.add(approval)
    session.flush()

    _append_line(
        {
            "event": "approval",
            "approval_id": approval.id,
            "contract_id": contract.id,
            "original_filename": contract.original_filename,
            "file_hash": contract.file_hash,
            "approved_by": approval.approved_by,
            "approved_at": approval.approved_at.isoformat(),
            "error_count_at_approval": error_count,
            "overridden": overridden,
            "pages_stamped": list(pages_stamped),
            "signature_hash": signature_hash,
            "ip_address": ip_address,
            "signed_in_as": signed_in_as,
        }
    )
    logger.info(
        "approval recorded contract=%s overridden=%s errors=%s",
        contract.id,
        overridden,
        error_count,
    )
    return approval


def record_execution(
    contract: Contract,
    *,
    pages_stamped: Sequence[int],
    executed_path: str,
    signature_hash: str | None,
) -> None:
    """Note the execution itself, so the log shows the stamp happened."""

    _append_line(
        {
            "event": "execution",
            "contract_id": contract.id,
            "original_filename": contract.original_filename,
            "executed_path": executed_path,
            "pages_stamped": list(pages_stamped),
            "signature_hash": signature_hash,
            "executed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
    )
    logger.info(
        "contract executed contract=%s pages=%s", contract.id, list(pages_stamped)
    )
