"""Extraction: flattened, fillable, mixed, and the awkward cases."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from app.services.config_store import FieldSpec, default_field_specs
from app.services.extract import extract, extract_text_fields, has_widgets, probe
from tests.conftest import (
    build_fillable_contract,
    build_flattened_contract,
    clean_values,
)


def spec(key: str, anchors: list[str], **kwargs) -> FieldSpec:
    return FieldSpec(field_key=key, label=key, anchors=anchors, **kwargs)


# --------------------------------------------------------------------------
# Path selection
# --------------------------------------------------------------------------


def test_flattened_contract_has_no_widgets(flattened_contract: Path) -> None:
    assert has_widgets(flattened_contract) is False


def test_fillable_contract_has_widgets(fillable_contract: Path) -> None:
    assert has_widgets(fillable_contract) is True


def test_flattened_uses_text_path(flattened_contract: Path) -> None:
    result = extract(flattened_contract, default_field_specs())
    assert result.source == "text"
    assert result.page_count == 4


def test_fillable_uses_acroform_path(fillable_contract: Path) -> None:
    result = extract(fillable_contract, default_field_specs())
    assert result.source == "acroform"


def test_mixed_falls_back_to_text_for_missing_widgets(tmp_path: Path) -> None:
    """A form with widgets for some fields and painted text for the rest."""

    path = build_fillable_contract(tmp_path / "mixed.pdf")
    doc = pymupdf.open(str(path))
    # Drop the SSN widget and paint the answer on instead, the way a
    # partially flattened envelope arrives.
    for page in doc:
        for widget in page.widgets() or []:
            if widget.field_name == "ssn":
                rect = widget.rect
                page.delete_widget(widget)
                page.insert_text(
                    (rect.x0, rect.y1 - 4), "123-45-6789", fontsize=10, fontname="helv"
                )
    mixed = tmp_path / "mixed_out.pdf"
    doc.save(str(mixed))
    doc.close()

    result = extract(mixed, default_field_specs())
    assert result.source == "acroform+text"
    assert result.value("ssn") == "123-45-6789"
    assert result.value("cdl_number") == "OH4471902"


# --------------------------------------------------------------------------
# Values
# --------------------------------------------------------------------------


@pytest.mark.parametrize("builder", [build_flattened_contract, build_fillable_contract])
def test_reads_every_default_field(builder, tmp_path: Path) -> None:
    path = builder(tmp_path / "contract.pdf")
    result = extract(path, default_field_specs())
    expected = clean_values()

    assert result.not_found == []
    for key, value in expected.items():
        assert result.value(key) == value, f"{key} extracted wrongly"


def test_records_the_page_each_value_came_from(flattened_contract: Path) -> None:
    result = extract(flattened_contract, default_field_specs())
    assert result.page("ssn") == 1
    assert result.page("cdl_expires") == 2
    assert result.page("emp1_company") == 3
    assert result.page("signature_date") == 4


def test_multi_word_label(flattened_contract: Path) -> None:
    values, _ = extract_text_fields(
        flattened_contract, [spec("dob", ["Date of Birth"])]
    )
    assert values["dob"] == clean_values()["dob"]


def test_label_present_with_no_value_is_found_but_blank(tmp_path: Path) -> None:
    """Different problem from a missing field, and reported differently."""

    path = build_flattened_contract(tmp_path / "blank.pdf", {"email": ""})
    result = extract(path, default_field_specs())

    assert "email" not in result.not_found
    assert result.value("email") == ""
    assert result.page("email") == 1


def test_field_genuinely_absent_is_not_found(flattened_contract: Path) -> None:
    result = extract(
        flattened_contract,
        [spec("medical_card_expires", ["Medical Examiner Certificate Expires"])],
    )
    assert result.not_found == ["medical_card_expires"]
    assert result.value("medical_card_expires") is None
    assert result.fields[0].found is False


def test_value_stops_at_the_next_column(tmp_path: Path) -> None:
    """Two label/value pairs on one line must not bleed into each other."""

    path = tmp_path / "columns.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((60, 120), "Date of Birth:", fontsize=10, fontname="helv")
    page.insert_text((160, 120), "01/02/1980", fontsize=10, fontname="helv")
    page.insert_text((320, 120), "SSN:", fontsize=10, fontname="helv")
    page.insert_text((360, 120), "123-45-6789", fontsize=10, fontname="helv")
    doc.save(str(path))
    doc.close()

    values, _ = extract_text_fields(
        path, [spec("dob", ["Date of Birth"]), spec("ssn", ["SSN"])]
    )
    assert values["dob"] == "01/02/1980"
    assert values["ssn"] == "123-45-6789"


def test_label_match_ignores_case_and_punctuation(tmp_path: Path) -> None:
    path = tmp_path / "punct.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((60, 120), "DATE OF BIRTH.:", fontsize=10, fontname="helv")
    page.insert_text((200, 120), "01/02/1980", fontsize=10, fontname="helv")
    doc.save(str(path))
    doc.close()

    values, _ = extract_text_fields(path, [spec("dob", ["date of birth"])])
    assert values["dob"] == "01/02/1980"


def test_underscore_rule_reads_as_blank_not_as_a_value(tmp_path: Path) -> None:
    path = build_flattened_contract(tmp_path / "rule.pdf", {"phone": ""})
    result = extract(path, default_field_specs())
    assert result.value("phone") == ""


def test_max_gap_stops_the_search(tmp_path: Path) -> None:
    """A value parked far to the right belongs to something else."""

    path = tmp_path / "gap.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((60, 120), "Email:", fontsize=10, fontname="helv")
    page.insert_text((500, 120), "far@example.com", fontsize=10, fontname="helv")
    doc.save(str(path))
    doc.close()

    near, _ = extract_text_fields(path, [spec("email", ["Email"], max_gap=500)])
    far, _ = extract_text_fields(path, [spec("email", ["Email"], max_gap=40)])
    assert near["email"] == "far@example.com"
    assert far["email"] == ""


def test_page_hint_restricts_the_search(flattened_contract: Path) -> None:
    """The CDL number is on page 2, so a hint of page 1 must not find it."""

    values, pages = extract_text_fields(
        flattened_contract, [spec("cdl_number", ["CDL Number"], page_hint=1)]
    )
    assert values == {}
    assert pages == {}

    found, _ = extract_text_fields(
        flattened_contract, [spec("cdl_number", ["CDL Number"], page_hint=2)]
    )
    assert found["cdl_number"] == clean_values()["cdl_number"]


# --------------------------------------------------------------------------
# Probe
# --------------------------------------------------------------------------


def test_probe_reports_widgets_on_a_fillable_pdf(fillable_contract: Path) -> None:
    result = probe(fillable_contract)
    names = {w.name for w in result.widgets}

    assert result.has_acroform is True
    assert result.page_count == 4
    assert {"ssn", "cdl_expires", "emp1_company"} <= names


def test_probe_never_returns_widget_values(fillable_contract: Path) -> None:
    """Probes run against real contracts. Those carry SSNs."""

    result = probe(fillable_contract)
    ssn = next(w for w in result.widgets if w.name == "ssn")

    assert ssn.has_value is True
    assert not hasattr(ssn, "value")


def test_probe_returns_page_text_on_a_flattened_pdf(flattened_contract: Path) -> None:
    result = probe(flattened_contract)

    assert result.has_acroform is False
    assert len(result.pages) == 4
    assert "Social Security Number" in result.pages[0].text
    assert "Carrier Representative" in result.pages[3].text
