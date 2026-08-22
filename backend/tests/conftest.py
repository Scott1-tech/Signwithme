"""Synthetic contract fixtures.

Real driver contracts contain Social Security numbers and must never be
committed. Every PDF in the test suite is generated here at test time with
PyMuPDF: one flattened (text painted on the page, like a completed DocuSign
envelope) and one still carrying AcroForm widgets.

Dates are relative to today so the suite does not rot. A CDL that expires
"in two years" stays valid next year too.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pymupdf
import pytest

TODAY = dt.date.today()


def days(offset: int) -> dt.date:
    return TODAY + dt.timedelta(days=offset)


def years(offset: float) -> dt.date:
    return TODAY + dt.timedelta(days=round(offset * 365.25))


def us(value: dt.date) -> str:
    return value.strftime("%m/%d/%Y")


# --------------------------------------------------------------------------
# A contract with nothing wrong with it
# --------------------------------------------------------------------------


def clean_values() -> dict[str, str]:
    return {
        "driver_name": "John Smith",
        "address": "1400 Harbor Road, Cleveland, OH 44114",
        "phone": "(216) 555-0142",
        "email": "jsmith@example.com",
        "dob": us(years(-38)),
        "ssn": "123-45-6789",
        "cdl_number": "OH4471902",
        "cdl_state": "OH",
        "cdl_issued": us(years(-3)),
        "cdl_expires": us(years(2)),
        "driver_signature": "John Smith",
        "signature_date": us(days(-2)),
        # Eleven years of continuous history, no gap over 30 days.
        "emp1_company": "Redline Freight Inc",
        "emp1_from": us(years(-4)),
        "emp1_to": "Present",
        "emp2_company": "Great Lakes Carriers",
        "emp2_from": us(years(-8)),
        "emp2_to": us(days(-1470)),
        "emp3_company": "Buckeye Transport Co",
        "emp3_from": us(years(-11)),
        "emp3_to": us(days(-2925)),
    }


#: (label, field_key) laid out page by page, mirroring a real packet.
PAGE_LAYOUT: list[list[tuple[str, str]]] = [
    [
        ("Driver Name", "driver_name"),
        ("Address", "address"),
        ("Phone", "phone"),
        ("Email", "email"),
        ("Date of Birth", "dob"),
        ("Social Security Number", "ssn"),
    ],
    [
        ("CDL Number", "cdl_number"),
        ("State of Issue", "cdl_state"),
        ("Issue Date", "cdl_issued"),
        ("Expiration Date", "cdl_expires"),
    ],
    [
        ("Employer 1", "emp1_company"),
        ("Employer 1 From", "emp1_from"),
        ("Employer 1 To", "emp1_to"),
        ("Employer 2", "emp2_company"),
        ("Employer 2 From", "emp2_from"),
        ("Employer 2 To", "emp2_to"),
        ("Employer 3", "emp3_company"),
        ("Employer 3 From", "emp3_from"),
        ("Employer 3 To", "emp3_to"),
    ],
    [
        ("Driver Signature", "driver_signature"),
        ("Date Signed", "signature_date"),
    ],
]

#: Which page each field lands on, 1-based.
PAGE_OF: dict[str, int] = {
    key: page for page, rows in enumerate(PAGE_LAYOUT, start=1) for _, key in rows
}

HEADINGS = [
    "Driver Application — Personal Information",
    "Commercial Driver's License",
    "Employment History — Previous 10 Years",
    "Certification and Signature",
]

LABEL_X = 60.0
VALUE_X = 230.0
FIRST_Y = 120.0
ROW_HEIGHT = 34.0


def build_flattened_contract(
    path: Path,
    values: dict[str, str] | None = None,
    *,
    carrier_anchor: bool = True,
) -> Path:
    """A contract whose answers are painted on, with no form fields left."""

    data = clean_values()
    if values:
        data.update(values)

    doc = pymupdf.open()
    for page_no, rows in enumerate(PAGE_LAYOUT):
        page = doc.new_page(width=612, height=792)
        page.insert_text((LABEL_X, 80), HEADINGS[page_no], fontsize=13, fontname="helv")

        y = FIRST_Y
        for label, key in rows:
            page.insert_text((LABEL_X, y), f"{label}:", fontsize=10, fontname="helv")
            value = data.get(key)
            if value:
                page.insert_text((VALUE_X, y), value, fontsize=10, fontname="helv")
            else:
                # A blank a driver skipped: the form still draws its rule.
                page.insert_text((VALUE_X, y), "_" * 28, fontsize=10, fontname="helv")
            y += ROW_HEIGHT

        if page_no == len(PAGE_LAYOUT) - 1 and carrier_anchor:
            page.insert_text(
                (LABEL_X, y + 40),
                "Carrier Representative:",
                fontsize=10,
                fontname="helv",
            )

    doc.save(str(path))
    doc.close()
    return path


def build_fillable_contract(
    path: Path,
    values: dict[str, str] | None = None,
    *,
    carrier_anchor: bool = True,
    carrier_fields: bool = True,
) -> Path:
    """A contract that still carries AcroForm widgets, named by field key."""

    data = clean_values()
    if values:
        data.update(values)

    doc = pymupdf.open()
    for page_no, rows in enumerate(PAGE_LAYOUT):
        page = doc.new_page(width=612, height=792)
        page.insert_text((LABEL_X, 80), HEADINGS[page_no], fontsize=13, fontname="helv")

        y = FIRST_Y
        for label, key in rows:
            page.insert_text((LABEL_X, y), f"{label}:", fontsize=10, fontname="helv")
            widget = pymupdf.Widget()
            widget.field_name = key
            widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
            widget.rect = pymupdf.Rect(VALUE_X, y - 11, VALUE_X + 250, y + 5)
            widget.field_value = data.get(key, "")
            widget.text_fontsize = 10
            page.add_widget(widget)
            y += ROW_HEIGHT

        if page_no == len(PAGE_LAYOUT) - 1:
            if carrier_anchor:
                page.insert_text(
                    (LABEL_X, y + 40),
                    "Carrier Representative:",
                    fontsize=10,
                    fontname="helv",
                )
            if carrier_fields:
                for offset, name in enumerate(("carrier_name", "carrier_rep_title")):
                    widget = pymupdf.Widget()
                    widget.field_name = name
                    widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
                    widget.rect = pymupdf.Rect(
                        320, y + 30 + offset * 24, 560, y + 46 + offset * 24
                    )
                    widget.field_value = ""
                    widget.text_fontsize = 10
                    page.add_widget(widget)

    doc.save(str(path))
    doc.close()
    return path


def build_signature_png(path: Path) -> Path:
    """A stand-in for the carrier representative's signature image."""

    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 300, 80), False)
    pixmap.set_rect(pixmap.irect, (255, 255, 255))
    pixmap.set_rect(pymupdf.IRect(10, 34, 290, 40), (20, 20, 90))
    pixmap.save(str(path))
    return path


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture
def flattened_contract(tmp_path: Path) -> Path:
    return build_flattened_contract(tmp_path / "flattened.pdf")


@pytest.fixture
def fillable_contract(tmp_path: Path) -> Path:
    return build_fillable_contract(tmp_path / "fillable.pdf")


@pytest.fixture
def signature_png(tmp_path: Path) -> Path:
    return build_signature_png(tmp_path / "signature.png")


def build_signed_contract(
    path: Path,
    values: dict[str, str] | None = None,
    *,
    signature: Path | None = None,
    signed_on: dt.date | None = None,
) -> Path:
    """A contract that has already been counter-signed.

    This is what a reviewer feeds the app to create a placement template:
    a finished contract with the carrier signature and date already on it.
    Built by running the real stamper over a flattened contract, so the
    detector is tested against the shape of output the app itself produces.
    """

    from app.services.config_store import SignatureConfig
    from app.services.stamp import apply, resolve_placements

    source = build_flattened_contract(path.with_name(f"unsigned_{path.name}"), values)
    image = signature or build_signature_png(path.with_name("template_signature.png"))

    apply(
        source,
        path,
        signature_png=image,
        placements=resolve_placements(source, SignatureConfig()),
        signed_on=signed_on or TODAY,
    )
    return path


@pytest.fixture
def signed_contract(tmp_path: Path) -> Path:
    return build_signed_contract(tmp_path / "signed.pdf")
