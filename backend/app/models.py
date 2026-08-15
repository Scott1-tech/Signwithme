"""Database tables, per specification section 5.

Two constraints are enforced here rather than left to convention:

* ``contracts`` never holds a full Social Security number. There are columns
  for the last four digits and a salted hash, and no column the full value
  could go in.
* ``approvals`` is append-only. Nothing in the app updates or deletes a row,
  and there is no route that could.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class ContractStatus:
    """The status model from specification section 3.

    ``executed`` is terminal. A contract is never edited after it reaches
    that state; a correction produces a new record linked by
    ``supersedes_id``.
    """

    UPLOADED = "uploaded"
    EXTRACTED = "extracted"
    NEEDS_REVIEW = "needs_review"
    CLEAN = "clean"
    APPROVED = "approved"
    EXECUTED = "executed"
    SUPERSEDED = "superseded"
    VOID = "void"

    ALL = (
        UPLOADED,
        EXTRACTED,
        NEEDS_REVIEW,
        CLEAN,
        APPROVED,
        EXECUTED,
        SUPERSEDED,
        VOID,
    )

    #: Only these may be deleted. Executed contracts are retained under
    #: 49 CFR 391.51.
    DELETABLE = (UPLOADED, VOID)


class Severity:
    ERROR = "error"
    WARNING = "warning"


class Contract(Base):
    __tablename__ = "contracts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    original_filename: Mapped[str] = mapped_column(String(512))
    stored_path: Mapped[str] = mapped_column(String(1024))
    executed_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    driver_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default=ContractStatus.UPLOADED, index=True
    )
    extraction_source: Mapped[str] = mapped_column(String(32), default="none")
    contract_type: Mapped[str] = mapped_column(String(64), default="owner_operator_plan_a")
    supersedes_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("contracts.id"), nullable=True
    )

    # Never the full number. See app.security.
    ssn_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    ssn_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )

    fields: Mapped[list["ExtractedField"]] = relationship(
        back_populates="contract",
        cascade="all, delete-orphan",
        order_by="ExtractedField.ordinal",
    )
    flags: Mapped[list["Flag"]] = relationship(
        back_populates="contract", cascade="all, delete-orphan"
    )
    approvals: Mapped[list["Approval"]] = relationship(
        back_populates="contract",
        cascade="all, delete-orphan",
        order_by="Approval.approved_at",
    )

    @property
    def error_count(self) -> int:
        return sum(
            1
            for flag in self.flags
            if flag.severity == Severity.ERROR and not flag.resolved
        )

    @property
    def warning_count(self) -> int:
        return sum(
            1
            for flag in self.flags
            if flag.severity == Severity.WARNING and not flag.resolved
        )

    @property
    def pages_to_fix(self) -> list[int]:
        pages = {
            flag.page
            for flag in self.flags
            if flag.severity == Severity.ERROR
            and not flag.resolved
            and flag.page is not None
        }
        return sorted(pages)

    @property
    def latest_approval(self) -> "Approval | None":
        return self.approvals[-1] if self.approvals else None


class ExtractedField(Base):
    __tablename__ = "extracted_fields"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    contract_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("contracts.id", ondelete="CASCADE"), index=True
    )
    field_key: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(256))
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    found: Mapped[bool] = mapped_column(Boolean, default=False)
    #: Preserves field-map order in the review table.
    ordinal: Mapped[int] = mapped_column(Integer, default=0)

    contract: Mapped[Contract] = relationship(back_populates="fields")


class Flag(Base):
    __tablename__ = "flags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    contract_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("contracts.id", ondelete="CASCADE"), index=True
    )
    field_key: Mapped[str] = mapped_column(String(64))
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    severity: Mapped[str] = mapped_column(String(16))
    rule_id: Mapped[str] = mapped_column(String(64), index=True)
    message: Mapped[str] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)

    contract: Mapped[Contract] = relationship(back_populates="flags")


class Approval(Base):
    """Append-only. The legal record behind every stamped signature."""

    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    contract_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("contracts.id", ondelete="CASCADE"), index=True
    )
    approved_by: Mapped[str] = mapped_column(String(256))
    approved_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    error_count_at_approval: Mapped[int] = mapped_column(Integer, default=0)
    overridden: Mapped[bool] = mapped_column(Boolean, default=False)
    pages_stamped: Mapped[Any] = mapped_column(JSON, default=list)
    signature_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)

    contract: Mapped[Contract] = relationship(back_populates="approvals")
