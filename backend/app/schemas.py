"""Request and response shapes, per specification section 6.

``lib/types.ts`` in the frontend mirrors this module. Change one, change the
other.
"""

from __future__ import annotations

import datetime as dt

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


class ContractListItem(BaseModel):
    id: str
    original_filename: str
    driver_name: str | None
    status: str
    page_count: int
    error_count: int
    warning_count: int
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


class AuditPage(BaseModel):
    items: list[AuditEntry]
    total: int
    page: int
    page_size: int
