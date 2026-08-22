"""Learning a placement template from a contract that was already signed."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pymupdf
import pytest

from app.services.stamp import Mark, apply_marks, preview_marks
from app.services.templates import analyze
from tests.conftest import (
    build_flattened_contract,
    build_signature_png,
    build_signed_contract,
    clean_values,
)


# --------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------


def test_finds_the_signature_that_was_stamped(signed_contract: Path) -> None:
    result = analyze(signed_contract)
    signatures = result.signatures

    assert len(signatures) == 1
    assert signatures[0].page == 4
    assert signatures[0].detected_as == "image"


def test_reports_the_page_geometry(signed_contract: Path) -> None:
    result = analyze(signed_contract)

    assert result.page_count == 4
    assert result.page_width == pytest.approx(612)
    assert result.page_height == pytest.approx(792)


def test_the_signature_mark_covers_where_the_image_sits(
    signed_contract: Path,
) -> None:
    mark = analyze(signed_contract).signatures[0]

    with pymupdf.open(str(signed_contract)) as doc:
        bbox = pymupdf.Rect(doc[3].get_image_info()[0]["bbox"])

    assert mark.x == pytest.approx(bbox.x0, abs=1)
    assert mark.y == pytest.approx(bbox.y0, abs=1)
    assert mark.width == pytest.approx(bbox.width, abs=1)


def test_labels_the_signature_with_the_text_beside_it(
    signed_contract: Path,
) -> None:
    """So the reviewer can tell one signature block from another."""

    mark = analyze(signed_contract).signatures[0]
    assert "Carrier Representative" in mark.sample_text


def test_finds_the_date_stamped_next_to_the_signature(
    signed_contract: Path,
) -> None:
    dates = analyze(signed_contract).dates

    assert len(dates) == 1
    assert dates[0].page == 4
    assert dates[0].detected_as == "date_text"


def test_never_mistakes_a_driver_date_for_a_signing_date(
    signed_contract: Path,
) -> None:
    """The contract is full of the driver's own dates.

    Stamping the carrier's date over a date of birth would alter what the
    driver attested to, so only dates in a signature's band are collected.
    """

    values = clean_values()
    detected = {mark.sample_text for mark in analyze(signed_contract).dates}

    for driver_date in (
        values["dob"],
        values["cdl_expires"],
        values["cdl_issued"],
        values["emp2_from"],
    ):
        assert driver_date not in detected

    # Pages that carry only driver dates contribute nothing at all.
    assert {mark.page for mark in analyze(signed_contract).marks} == {4}


def test_every_date_can_be_reported_when_asked(signed_contract: Path) -> None:
    wide = analyze(signed_contract, dates_beside_signatures=False)
    assert len(wide.dates) > 1
    assert {mark.page for mark in wide.dates} > {4}


def test_dates_can_be_switched_off(signed_contract: Path) -> None:
    assert analyze(signed_contract, include_dates=False).dates == []


def test_an_unsigned_contract_yields_no_marks(flattened_contract: Path) -> None:
    result = analyze(flattened_contract)
    assert result.marks == []


def test_a_multi_word_date_is_one_mark(tmp_path: Path) -> None:
    """"March 1, 2025" must not also leave "2025" behind."""

    path = tmp_path / "wordy.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_image(
        pymupdf.Rect(60, 300, 210, 332),
        filename=str(build_signature_png(tmp_path / "sig.png")),
    )
    page.insert_text((240, 322), "March 1, 2025", fontsize=10, fontname="helv")
    doc.save(str(path))
    doc.close()

    dates = analyze(path).dates
    assert len(dates) == 1
    assert dates[0].sample_text == "March 1, 2025"


def test_a_page_sized_image_is_not_a_signature(tmp_path: Path) -> None:
    """A scanned page is a page, not somebody's name."""

    path = tmp_path / "scan.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_image(
        pymupdf.Rect(0, 0, 612, 792),
        filename=str(build_signature_png(tmp_path / "big.png")),
    )
    doc.save(str(path))
    doc.close()

    assert analyze(path).signatures == []


# --------------------------------------------------------------------------
# Applying a template
# --------------------------------------------------------------------------


def test_marks_stamp_onto_a_fresh_contract(tmp_path: Path) -> None:
    template_source = build_signed_contract(tmp_path / "template.pdf")
    marks = [
        Mark(m.kind, m.page, m.x, m.y, m.width, m.height)
        for m in analyze(template_source).marks
    ]

    fresh = build_flattened_contract(tmp_path / "fresh.pdf", {"phone": "2165550111"})
    executed = tmp_path / "executed.pdf"

    result = apply_marks(
        fresh,
        executed,
        signature_png=build_signature_png(tmp_path / "sig2.png"),
        marks=marks,
        sign_date=dt.date(2026, 5, 4),
    )

    assert result.pages_stamped == [4]
    assert result.dates_stamped == [4]

    with pymupdf.open(str(executed)) as doc:
        assert len(doc[3].get_images()) == 1
        assert "05/04/2026" in doc[3].get_text()


def test_the_signature_lands_where_the_template_had_it(tmp_path: Path) -> None:
    template_source = build_signed_contract(tmp_path / "template.pdf")
    original = analyze(template_source).signatures[0]

    marks = [Mark("signature", original.page, original.x, original.y,
                  original.width, original.height)]
    fresh = build_flattened_contract(tmp_path / "fresh.pdf")
    executed = tmp_path / "executed.pdf"

    apply_marks(
        fresh,
        executed,
        signature_png=build_signature_png(tmp_path / "sig2.png"),
        marks=marks,
        sign_date=dt.date(2026, 5, 4),
    )

    with pymupdf.open(str(executed)) as doc:
        landed = pymupdf.Rect(doc[3].get_image_info()[0]["bbox"])

    assert landed.x0 == pytest.approx(original.x, abs=1.5)
    assert landed.y0 == pytest.approx(original.y, abs=1.5)


def test_marks_scale_onto_a_larger_page(tmp_path: Path) -> None:
    """A letter template applied to a legal page must not miss the box."""

    legal = tmp_path / "legal.pdf"
    doc = pymupdf.open()
    for _ in range(4):
        doc.new_page(width=612, height=1008)
    doc.save(str(legal))
    doc.close()

    marks = [Mark("signature", 4, 60.0, 396.0, 150.0, 32.0)]
    executed = tmp_path / "executed.pdf"

    apply_marks(
        legal,
        executed,
        signature_png=build_signature_png(tmp_path / "sig.png"),
        marks=marks,
        source_page_size=(612.0, 792.0),
    )

    with pymupdf.open(str(executed)) as out:
        landed = pymupdf.Rect(out[3].get_image_info()[0]["bbox"])

    # Half way down a letter page is half way down a legal page.
    assert landed.y0 == pytest.approx(396.0 * (1008 / 792), abs=2)


def test_a_mark_for_a_page_the_contract_lacks_is_skipped(tmp_path: Path) -> None:
    short = tmp_path / "short.pdf"
    doc = pymupdf.open()
    doc.new_page()
    doc.save(str(short))
    doc.close()

    result = apply_marks(
        short,
        tmp_path / "executed.pdf",
        signature_png=build_signature_png(tmp_path / "sig.png"),
        marks=[Mark("signature", 1, 60, 400, 150, 32), Mark("signature", 9, 60, 400, 150, 32)],
    )

    assert result.pages_stamped == [1]


def test_apply_marks_refuses_to_overwrite_the_original(tmp_path: Path) -> None:
    fresh = build_flattened_contract(tmp_path / "fresh.pdf")
    with pytest.raises(ValueError, match="original upload"):
        apply_marks(
            fresh,
            fresh,
            signature_png=build_signature_png(tmp_path / "sig.png"),
            marks=[Mark("signature", 1, 60, 400, 150, 32)],
        )


def test_apply_marks_refuses_an_empty_template(tmp_path: Path) -> None:
    fresh = build_flattened_contract(tmp_path / "fresh.pdf")
    with pytest.raises(ValueError, match="no marks"):
        apply_marks(
            fresh,
            tmp_path / "executed.pdf",
            signature_png=build_signature_png(tmp_path / "sig.png"),
            marks=[],
        )


def test_a_signature_mark_without_an_image_is_refused(tmp_path: Path) -> None:
    fresh = build_flattened_contract(tmp_path / "fresh.pdf")
    with pytest.raises(ValueError, match="none was chosen"):
        apply_marks(
            fresh,
            tmp_path / "executed.pdf",
            signature_png=None,
            marks=[Mark("signature", 1, 60, 400, 150, 32)],
        )


def test_a_date_only_template_needs_no_signature(tmp_path: Path) -> None:
    fresh = build_flattened_contract(tmp_path / "fresh.pdf")
    result = apply_marks(
        fresh,
        tmp_path / "executed.pdf",
        signature_png=None,
        marks=[Mark("date", 1, 300, 400, 80, 12)],
        sign_date=dt.date(2026, 5, 4),
    )

    assert result.pages_stamped == []
    assert result.dates_stamped == [1]


def test_the_driver_answers_survive_stamping(tmp_path: Path) -> None:
    fresh = build_flattened_contract(tmp_path / "fresh.pdf")
    executed = tmp_path / "executed.pdf"

    apply_marks(
        fresh,
        executed,
        signature_png=build_signature_png(tmp_path / "sig.png"),
        marks=[Mark("signature", 4, 60, 300, 150, 32)],
        sign_date=dt.date(2026, 5, 4),
    )

    with pymupdf.open(str(executed)) as doc:
        text = "".join(page.get_text() for page in doc)

    values = clean_values()
    assert values["driver_name"] in text
    assert values["dob"] in text
    assert values["cdl_number"] in text


# --------------------------------------------------------------------------
# Preview
# --------------------------------------------------------------------------


def test_preview_draws_the_marks(signed_contract: Path) -> None:
    marks = [
        Mark(m.kind, m.page, m.x, m.y, m.width, m.height)
        for m in analyze(signed_contract).marks
    ]

    plain = preview_marks(signed_contract, 4, [])
    boxed = preview_marks(signed_contract, 4, marks)

    assert plain.startswith(b"\x89PNG")
    assert plain != boxed


def test_preview_rejects_a_page_out_of_range(signed_contract: Path) -> None:
    with pytest.raises(IndexError):
        preview_marks(signed_contract, 99, [])
