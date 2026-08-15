"""Runtime app configuration: the field map, carrier details, placement.

Stored as JSON on disk rather than in the database. It is a handful of
records that one person edits on the settings screen, and keeping it as a
readable file means the reviewer can back it up, diff it, or hand-edit it
when a contract revision moves a label.

Canonical field keys are the contract between the field map and the rules
engine. ``rules.py`` looks for ``cdl_expires``; the field map says where
``cdl_expires`` lives in this particular PDF. Renaming a canonical key
breaks the rules, so treat the keys below as fixed and change the ``label``
and ``anchors`` instead.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.config import get_settings

DEFAULT_CONTRACT_TYPE = "owner_operator_plan_a"


# --------------------------------------------------------------------------
# Field map
# --------------------------------------------------------------------------


class FieldSpec(BaseModel):
    """How to find one canonical field inside a contract PDF."""

    field_key: str
    label: str
    #: Exact AcroForm widget name, when the returned PDF still has fields.
    acroform_name: str | None = None
    #: Label phrases to search for in flattened text, best first.
    anchors: list[str] = Field(default_factory=list)
    required: bool = True
    #: Maximum horizontal distance, in points, to keep collecting words to
    #: the right of the label before deciding the value has ended.
    max_gap: float = 320.0
    #: Restrict the text search to one 1-based page when a label is common.
    page_hint: int | None = None

    @field_validator("field_key")
    @classmethod
    def _key_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("field_key cannot be blank")
        return value


def _f(
    key: str,
    label: str,
    anchors: list[str],
    *,
    acroform: str | None = None,
    required: bool = True,
) -> FieldSpec:
    return FieldSpec(
        field_key=key,
        label=label,
        acroform_name=acroform or key,
        anchors=anchors,
        required=required,
    )


def default_field_specs() -> list[FieldSpec]:
    """A starting field map for a typical owner-operator packet.

    These anchors are a guess at how the form is worded. Day one of the build
    plan is running ``POST /config/probe`` against a real contract and
    correcting them — see open question 2 in the specification.

    Employment fields are deliberately ``required=False``. The employment
    rules own that domain: ``employment.none`` already reports a history that
    could not be read at all, and marking each ``empN_*`` field required as
    well would emit two flags for one problem.
    """

    specs = [
        _f("driver_name", "Driver Name", ["Driver Name", "Name of Applicant", "Applicant Name"]),
        _f("address", "Address", ["Address", "Home Address", "Street Address"], required=False),
        _f("phone", "Phone", ["Phone", "Telephone", "Phone Number", "Cell Phone"]),
        _f("email", "Email", ["Email", "E-mail", "Email Address"]),
        _f("dob", "Date of Birth", ["Date of Birth", "DOB", "Birth Date"]),
        _f("ssn", "Social Security Number", ["Social Security Number", "SSN", "Social Security No"]),
        _f("cdl_number", "CDL Number", ["CDL Number", "Driver's License Number", "License Number", "CDL No"]),
        _f("cdl_state", "CDL State", ["State of Issue", "License State", "CDL State", "Issuing State"]),
        _f("cdl_issued", "CDL Issue Date", ["Issue Date", "Date Issued", "Issued"]),
        _f("cdl_expires", "CDL Expiration Date", ["Expiration Date", "Expires", "Exp Date"]),
        _f("driver_signature", "Driver Signature", ["Driver Signature", "Signature of Driver", "Applicant Signature"]),
        _f("signature_date", "Date Signed", ["Date Signed", "Signature Date"]),
    ]

    for n in (1, 2, 3):
        specs.extend(
            [
                _f(
                    f"emp{n}_company",
                    f"Employer {n} — Company",
                    [f"Employer {n}", f"Company Name {n}", f"Employer {n} Name"],
                    required=False,
                ),
                _f(
                    f"emp{n}_from",
                    f"Employer {n} — From",
                    [f"Employer {n} From", f"From {n}"],
                    required=False,
                ),
                _f(
                    f"emp{n}_to",
                    f"Employer {n} — To",
                    [f"Employer {n} To", f"To {n}"],
                    required=False,
                ),
            ]
        )
    return specs


class FieldMap(BaseModel):
    """Field specs keyed by contract type."""

    contract_types: dict[str, list[FieldSpec]] = Field(default_factory=dict)

    def for_type(self, contract_type: str) -> list[FieldSpec]:
        if contract_type in self.contract_types:
            return self.contract_types[contract_type]
        if DEFAULT_CONTRACT_TYPE in self.contract_types:
            return self.contract_types[DEFAULT_CONTRACT_TYPE]
        return default_field_specs()

    @classmethod
    def default(cls) -> "FieldMap":
        return cls(contract_types={DEFAULT_CONTRACT_TYPE: default_field_specs()})


# --------------------------------------------------------------------------
# Signature placement
# --------------------------------------------------------------------------


class SignatureConfig(BaseModel):
    """Where the carrier signature lands, for one contract type.

    Anchor mode searches every page for ``anchor_phrase`` and stamps relative
    to the first hit on each page, so it survives the page shifts that happen
    when a contract is revised. Offset mode is the fallback: fractions of page
    width and height, which works on letter and legal alike.
    """

    mode: Literal["anchor", "offset"] = "anchor"

    # Anchor mode
    anchor_phrase: str = "Carrier Representative"
    #: Offsets in points from the top-left of the matched phrase.
    dx: float = 0.0
    dy: float = 6.0
    fallback_to_offset: bool = True

    # Offset mode
    #: 1-based pages to stamp. Negative counts from the end, so -1 is the
    #: last page. Only used in offset mode, or as the anchor fallback.
    offset_pages: list[int] = Field(default_factory=lambda: [-1])
    offset_x_frac: float = 0.08
    offset_y_frac: float = 0.78

    # Shared
    width: float = 150.0
    height: float = 32.0
    #: Stop after this many pages, so a runaway anchor cannot stamp all 52.
    max_stamps: int = 12

    # Date beside the signature
    stamp_date: bool = True
    date_dx: float = 165.0
    date_dy: float = 10.0
    date_format: str = "%m/%d/%Y"
    date_font_size: float = 10.0


class CarrierConfig(BaseModel):
    """Company values, plus signature placement per contract type."""

    carrier_name: str = ""
    representative_name: str = ""
    representative_title: str = ""
    mc_number: str = ""
    dot_number: str = ""

    #: Carrier-side AcroForm fields to fill on execution, widget name to
    #: value. Only carrier fields belong here: the app never edits what the
    #: driver attested to.
    acroform_fills: dict[str, str] = Field(default_factory=dict)

    #: Filename of the uploaded signature PNG, inside the signatures dir.
    signature_file: str | None = None

    placements: dict[str, SignatureConfig] = Field(
        default_factory=lambda: {DEFAULT_CONTRACT_TYPE: SignatureConfig()}
    )

    def placement_for(self, contract_type: str) -> SignatureConfig:
        return (
            self.placements.get(contract_type)
            or self.placements.get(DEFAULT_CONTRACT_TYPE)
            or SignatureConfig()
        )


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------


def _read(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # A corrupt config file should not take the app down; fall back to
        # defaults and let the reviewer re-save from the settings screen.
        return None


def _write(path: Path, payload: BaseModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(payload.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(path)


def _field_map_path() -> Path:
    return get_settings().config_dir / "field_map.json"


def _carrier_path() -> Path:
    return get_settings().config_dir / "carrier.json"


def load_field_map() -> FieldMap:
    raw = _read(_field_map_path())
    if raw is None:
        return FieldMap.default()
    try:
        field_map = FieldMap.model_validate(raw)
    except ValueError:
        return FieldMap.default()
    return field_map if field_map.contract_types else FieldMap.default()


def save_field_map(field_map: FieldMap) -> FieldMap:
    _write(_field_map_path(), field_map)
    return field_map


def load_carrier() -> CarrierConfig:
    raw = _read(_carrier_path())
    if raw is None:
        return CarrierConfig()
    try:
        return CarrierConfig.model_validate(raw)
    except ValueError:
        return CarrierConfig()


def save_carrier(carrier: CarrierConfig) -> CarrierConfig:
    _write(_carrier_path(), carrier)
    return carrier


def signature_path() -> Path | None:
    """Absolute path of the configured signature PNG, if one is uploaded."""

    carrier = load_carrier()
    if not carrier.signature_file:
        return None
    path = get_settings().signatures_dir / carrier.signature_file
    return path if path.exists() else None
