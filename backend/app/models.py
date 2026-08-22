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

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
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

    # What the reviewer chose when uploading: which completed contract to
    # copy the placement from, which signature to stamp, and the date to
    # write beside it.
    template_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("templates.id"), nullable=True
    )
    signature_asset_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("signature_assets.id"), nullable=True
    )
    sign_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)

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
    template: Mapped["Template | None"] = relationship(
        foreign_keys=[template_id], lazy="joined"
    )
    signature_asset: Mapped["SignatureAsset | None"] = relationship(
        foreign_keys=[signature_asset_id], lazy="joined"
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


class MarkKind:
    """What a template mark tells the stamper to draw."""

    SIGNATURE = "signature"
    DATE = "date"

    ALL = (SIGNATURE, DATE)


class SignatureAsset(Base):
    """One saved signature image.

    A carrier may have several people who sign, so signatures are a library
    rather than a single configured file. The reviewer picks one when
    uploading a contract.
    """

    __tablename__ = "signature_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(128))
    filename: Mapped[str] = mapped_column(String(256))
    file_hash: Mapped[str] = mapped_column(String(64))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class Template(Base):
    """Where the signature and date go, learned from a completed contract.

    The reviewer uploads a contract that has already been signed correctly.
    The app finds the signature images and dates already on it and records
    their positions. Every later contract of that kind is stamped in the
    same places, so nobody has to describe coordinates by hand.

    The source PDF is kept so the marks can be previewed and adjusted.
    """

    __tablename__ = "templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    source_filename: Mapped[str] = mapped_column(String(512))
    source_path: Mapped[str] = mapped_column(String(1024))
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    #: Page size of the source, so marks can be scaled onto a contract
    #: printed at a different size.
    page_width: Mapped[float] = mapped_column(default=612.0)
    page_height: Mapped[float] = mapped_column(default=792.0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )

    marks: Mapped[list["TemplateMark"]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="TemplateMark.page, TemplateMark.ordinal",
    )

    @property
    def signature_marks(self) -> list["TemplateMark"]:
        return [m for m in self.marks if m.kind == MarkKind.SIGNATURE and m.enabled]

    @property
    def date_marks(self) -> list["TemplateMark"]:
        return [m for m in self.marks if m.kind == MarkKind.DATE and m.enabled]

    @property
    def pages_marked(self) -> list[int]:
        return sorted({m.page for m in self.marks if m.enabled})


class TemplateMark(Base):
    """One place on one page where something gets stamped."""

    __tablename__ = "template_marks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    template_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("templates.id", ondelete="CASCADE"), index=True
    )
    #: "signature" or "date".
    kind: Mapped[str] = mapped_column(String(16))
    page: Mapped[int] = mapped_column(Integer)
    x: Mapped[float] = mapped_column()
    y: Mapped[float] = mapped_column()
    width: Mapped[float] = mapped_column()
    height: Mapped[float] = mapped_column()
    #: How this mark was found: "image", "date_text", or "manual".
    detected_as: Mapped[str] = mapped_column(String(24), default="manual")
    #: The text that was there in the source, for dates. Shown in the UI so
    #: the reviewer can recognise the spot.
    sample_text: Mapped[str] = mapped_column(String(256), default="")
    #: A reviewer can switch off a detection that was a false positive
    #: without deleting it.
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    ordinal: Mapped[int] = mapped_column(Integer, default=0)

    template: Mapped[Template] = relationship(back_populates="marks")
