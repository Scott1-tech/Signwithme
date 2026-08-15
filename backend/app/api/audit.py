"""Audit routes. Read-only, by design.

``approvals`` is append-only: there is no update route and no delete route
here, and there must never be one.
"""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Approval, Contract
from app.schemas import AuditEntry, AuditPage

router = APIRouter(prefix="/audit", tags=["audit"])

CSV_COLUMNS = [
    "approved_at",
    "approved_by",
    "driver_name",
    "original_filename",
    "contract_id",
    "contract_status",
    "overridden",
    "error_count_at_approval",
    "pages_stamped",
    "signature_hash",
    "ip_address",
]


def _rows(session: Session, limit: int | None = None, offset: int = 0):
    query = (
        select(Approval, Contract)
        .join(Contract, Contract.id == Approval.contract_id, isouter=True)
        .order_by(Approval.approved_at.desc())
    )
    if limit is not None:
        query = query.offset(offset).limit(limit)
    return session.execute(query).all()


def _to_entry(approval: Approval, contract: Contract | None) -> AuditEntry:
    return AuditEntry(
        id=approval.id,
        contract_id=approval.contract_id,
        original_filename=contract.original_filename if contract else None,
        driver_name=contract.driver_name if contract else None,
        contract_status=contract.status if contract else None,
        approved_by=approval.approved_by,
        approved_at=approval.approved_at,
        error_count_at_approval=approval.error_count_at_approval,
        overridden=approval.overridden,
        pages_stamped=list(approval.pages_stamped or []),
        signature_hash=approval.signature_hash,
        ip_address=approval.ip_address,
    )


@router.get("", response_model=AuditPage)
def list_audit(
    page: int = 1, page_size: int = 50, session: Session = Depends(get_db)
) -> AuditPage:
    page = max(1, page)
    page_size = min(max(1, page_size), 200)

    total = session.scalar(select(func.count()).select_from(Approval)) or 0
    rows = _rows(session, limit=page_size, offset=(page - 1) * page_size)

    return AuditPage(
        items=[_to_entry(approval, contract) for approval, contract in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/export")
def export_audit(session: Session = Depends(get_db)) -> StreamingResponse:
    """The whole log as CSV, for an auditor who wants it in a spreadsheet."""

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS)
    writer.writeheader()

    for approval, contract in _rows(session):
        entry = _to_entry(approval, contract)
        writer.writerow(
            {
                "approved_at": entry.approved_at.isoformat(),
                "approved_by": entry.approved_by,
                "driver_name": entry.driver_name or "",
                "original_filename": entry.original_filename or "",
                "contract_id": entry.contract_id,
                "contract_status": entry.contract_status or "",
                "overridden": "yes" if entry.overridden else "no",
                "error_count_at_approval": entry.error_count_at_approval,
                "pages_stamped": " ".join(str(p) for p in entry.pages_stamped),
                "signature_hash": entry.signature_hash or "",
                "ip_address": entry.ip_address or "",
            }
        )

    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="approvals.csv"',
        },
    )
