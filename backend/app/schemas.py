"""Request and response shapes, per specification section 6.

``lib/types.ts`` in the frontend mirrors this module. Change one, change the
other.
"""

from __future__ import annotations

import datetime as dt

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.services.config_store import CarrierConfig, FieldMap, FieldSpec, SignatureConfig

#: Values the API masks before returning them. The full Social Security
#: number exists only inside the PDF on disk; nothing else may echo it.
SENSITIVE_FIELD_KEYS = frozenset({"ssn"})


# --------------------------------------------------------------------------
# Contract pieces
# --------------------------------------------------------------------------


class FieldOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    field_key: str
    label: str
    value: str | None
    page: int | None
    found: bool


class FlagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    rule_id: str
    field_key: str
    page: int | None
    severity: str
    message: str
    resolved: bool


class PlacementOut(BaseModel):
    page: int
    x: float
    y: float
    width: float
    height: float
    how: str


class SummaryOut(BaseModel):
    error_count: int
    warning_count: int
    pages_to_fix: list[int]


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    contract_id: str
    approved_by: str
    approved_at: dt.datetime
    error_count_at_approval: int
    overridden: bool
    pages_stamped: list[int]
    signature_hash: str | None
    ip_address: str | None
    #: The account signed in at the time, when the desk has accounts.
    signed_in_as: str | None = None


class ContractListItem(BaseModel):
    id: str
    original_filename: str
    driver_name: str | None
    status: str
    page_count: int
    error_count: int
    warning_count: int
    template_name: str | None = None
    signature_name: str | None = None
    sign_date: dt.date | None = None
    created_at: dt.datetime
    updated_at: dt.datetime


class ContractDetail(BaseModel):
    id: str
    original_filename: str
    status: str
    page_count: int
    driver_name: str | None
    extraction_source: str
    contract_type: str
    supersedes_id: str | None
    superseded_by_id: str | None = None
    ssn_masked: str | None

    # What the reviewer chose at upload time.
    template_id: str | None = None
    template_name: str | None = None
    signature_asset_id: str | None = None
    signature_name: str | None = None
    sign_date: dt.date | None = None
    created_at: dt.datetime
    updated_at: dt.datetime

    summary: SummaryOut
    fields: list[FieldOut]
    flags: list[FlagOut]
    placements: list[PlacementOut]

    can_approve: bool
    can_execute: bool
    #: False when no signature PNG is configured yet, so the UI can say why
    #: execution is unavailable instead of failing at the last click.
    signature_ready: bool
    approval: ApprovalOut | None = None


class ContractPage(BaseModel):
    items: list[ContractListItem]
    total: int
    page: int
    page_size: int


# --------------------------------------------------------------------------
# Requests
# --------------------------------------------------------------------------


class ApproveRequest(BaseModel):
    approved_by: str = Field(min_length=1, max_length=256)
    #: Must be true to approve a contract with unresolved errors. The
    #: approval is then recorded as an override.
    acknowledge_errors: bool = False


class FlagResolveRequest(BaseModel):
    resolved: bool = True


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


class FieldMapOut(BaseModel):
    contract_types: dict[str, list[FieldSpec]]

    @classmethod
    def of(cls, field_map: FieldMap) -> "FieldMapOut":
        return cls(contract_types=field_map.contract_types)


class CarrierOut(CarrierConfig):
    #: Whether a signature image has actually been uploaded.
    signature_uploaded: bool = False


class TestPlacementRequest(BaseModel):
    contract_id: str
    page: int | None = None
    signature: SignatureConfig


class ProbeWidgetOut(BaseModel):
    page: int
    name: str
    type: str
    has_value: bool


class ProbePageOut(BaseModel):
    page: int
    text: str


class ProbeOut(BaseModel):
    page_count: int
    has_acroform: bool
    widgets: list[ProbeWidgetOut]
    pages: list[ProbePageOut]


# --------------------------------------------------------------------------
# Audit
# --------------------------------------------------------------------------


class AuditEntry(BaseModel):
    id: str
    contract_id: str
    original_filename: str | None
    driver_name: str | None
    contract_status: str | None
    approved_by: str
    approved_at: dt.datetime
    error_count_at_approval: int
    overridden: bool
    pages_stamped: list[int]
    signature_hash: str | None
    ip_address: str | None
    signed_in_as: str | None = None


class AuditPage(BaseModel):
    items: list[AuditEntry]
    total: int
    page: int
    page_size: int


# --------------------------------------------------------------------------
# Signature library
# --------------------------------------------------------------------------


class SignatureAssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    file_hash: str
    is_default: bool
    created_at: dt.datetime


class SignatureRename(BaseModel):
    name: str = Field(min_length=1, max_length=128)


# --------------------------------------------------------------------------
# Placement templates
# --------------------------------------------------------------------------


class TemplateMarkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    page: int
    x: float
    y: float
    width: float
    height: float
    detected_as: str
    sample_text: str
    enabled: bool


class TemplateMarkIn(BaseModel):
    """A mark as edited by the reviewer. Without an id it is a new one."""

    id: str | None = None
    kind: Literal["signature", "date"]
    page: int = Field(ge=1)
    x: float
    y: float
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    sample_text: str = ""
    enabled: bool = True


class TemplateOut(BaseModel):
    id: str
    name: str
    description: str
    source_filename: str
    page_count: int
    page_width: float
    page_height: float
    created_at: dt.datetime
    updated_at: dt.datetime
    marks: list[TemplateMarkOut]
    signature_count: int
    date_count: int
    pages_marked: list[int]
    #: False when nothing is enabled, so the UI can say a template is not
    #: usable yet rather than failing at stamping time.
    ready: bool


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    marks: list[TemplateMarkIn] | None = None


class TemplateListItem(BaseModel):
    id: str
    name: str
    description: str
    source_filename: str
    page_count: int
    signature_count: int
    date_count: int
    pages_marked: list[int]
    ready: bool
    created_at: dt.datetime
