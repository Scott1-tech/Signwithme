"""Signature placement, stamping, and page rendering."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pymupdf
import pytest

from app.services.config_store import SignatureConfig
from app.services.stamp import Placement, apply, preview_page, resolve_placements
from tests.conftest import (
    build_fillable_contract,
    build_flattened_contract,
    build_signature_png,
)


# --------------------------------------------------------------------------
# Placement
# --------------------------------------------------------------------------


def test_anchor_mode_finds_the_carrier_phrase(flattened_contract: Path) -> None:
    placements = resolve_placements(flattened_contract, SignatureConfig())

    assert len(placements) == 1
    assert placements[0].page == 4
    assert placements[0].how == "anchor"


def test_anchor_offsets_are_applied(flattened_contract: Path) -> None:
    plain = resolve_placements(flattened_contract, SignatureConfig(dx=0, dy=0))[0]
    shifted = resolve_placements(flattened_contract, SignatureConfig(dx=25, dy=40))[0]

    assert shifted.x == pytest.approx(plain.x + 25)
    assert shifted.y == pytest.approx(plain.y + 40)


def test_anchor_falls_back_to_offset_when_the_phrase_is_absent(tmp_path: Path) -> None:
    path = build_flattened_contract(tmp_path / "no_anchor.pdf", carrier_anchor=False)
    placements = resolve_placements(path, SignatureConfig(fallback_to_offset=True))

    assert [p.how for p in placements] == ["offset"]
    assert placements[0].page == 4


def test_anchor_without_fallback_resolves_nothing(tmp_path: Path) -> None:
    path = build_flattened_contract(tmp_path / "no_anchor.pdf", carrier_anchor=False)
    assert resolve_placements(path, SignatureConfig(fallback_to_offset=False)) == []


def test_offset_mode_uses_fractions_of_the_page(flattened_contract: Path) -> None:
    config = SignatureConfig(
        mode="offset", offset_pages=[1], offset_x_frac=0.25, offset_y_frac=0.5
    )
    placement = resolve_placements(flattened_contract, config)[0]

    assert placement.x == pytest.approx(612 * 0.25)
    assert placement.y == pytest.approx(792 * 0.5)
    assert placement.how == "offset"


def test_offset_page_minus_one_means_the_last_page(flattened_contract: Path) -> None:
    config = SignatureConfig(mode="offset", offset_pages=[-1])
    assert resolve_placements(flattened_contract, config)[0].page == 4


def test_offset_pages_out_of_range_are_dropped(flattened_contract: Path) -> None:
    config = SignatureConfig(mode="offset", offset_pages=[2, 99, 0, -1])
    assert [p.page for p in resolve_placements(flattened_contract, config)] == [2, 4]


def test_anchor_stamps_every_page_that_carries_the_phrase(tmp_path: Path) -> None:
    path = tmp_path / "multi.pdf"
    doc = pymupdf.open()
    for _ in range(3):
        page = doc.new_page()
        page.insert_text((60, 700), "Carrier Representative:", fontsize=10)
    doc.save(str(path))
    doc.close()

    placements = resolve_placements(path, SignatureConfig())
    assert [p.page for p in placements] == [1, 2, 3]


def test_max_stamps_caps_a_runaway_anchor(tmp_path: Path) -> None:
    path = tmp_path / "many.pdf"
    doc = pymupdf.open()
    for _ in range(10):
        page = doc.new_page()
        page.insert_text((60, 700), "Carrier Representative:", fontsize=10)
    doc.save(str(path))
    doc.close()

    placements = resolve_placements(path, SignatureConfig(max_stamps=4))
    assert len(placements) == 4


# --------------------------------------------------------------------------
# Stamping
# --------------------------------------------------------------------------


def test_apply_writes_a_new_file_and_leaves_the_original_alone(
    flattened_contract: Path, signature_png: Path, tmp_path: Path
) -> None:
    before = flattened_contract.read_bytes()
    executed = tmp_path / "executed.pdf"

    result = apply(
        flattened_contract,
        executed,
        signature_png=signature_png,
        placements=resolve_placements(flattened_contract, SignatureConfig()),
    )

    assert executed.exists()
    assert result.pages_stamped == [4]
    assert flattened_contract.read_bytes() == before


def test_apply_refuses_to_overwrite_the_upload(
    flattened_contract: Path, signature_png: Path
) -> None:
    with pytest.raises(ValueError, match="original upload"):
        apply(
            flattened_contract,
            flattened_contract,
            signature_png=signature_png,
            placements=resolve_placements(flattened_contract, SignatureConfig()),
        )


def test_apply_refuses_when_nothing_resolved(
    flattened_contract: Path, signature_png: Path, tmp_path: Path
) -> None:
    with pytest.raises(ValueError, match="placements"):
        apply(
            flattened_contract,
            tmp_path / "executed.pdf",
            signature_png=signature_png,
            placements=[],
        )


def test_the_signature_image_lands_on_the_page(
    flattened_contract: Path, signature_png: Path, tmp_path: Path
) -> None:
    executed = tmp_path / "executed.pdf"
    apply(
        flattened_contract,
        executed,
        signature_png=signature_png,
        placements=resolve_placements(flattened_contract, SignatureConfig()),
    )

    with pymupdf.open(str(executed)) as doc:
        assert len(doc[3].get_images()) == 1
        assert len(doc[0].get_images()) == 0


def test_the_date_is_stamped_beside_the_signature(
    flattened_contract: Path, signature_png: Path, tmp_path: Path
) -> None:
    executed = tmp_path / "executed.pdf"
    signed_on = dt.date(2026, 3, 9)
    apply(
        flattened_contract,
        executed,
        signature_png=signature_png,
        placements=resolve_placements(flattened_contract, SignatureConfig()),
        signed_on=signed_on,
    )

    with pymupdf.open(str(executed)) as doc:
        assert "03/09/2026" in doc[3].get_text()


def test_the_date_can_be_switched_off(
    flattened_contract: Path, signature_png: Path, tmp_path: Path
) -> None:
    executed = tmp_path / "executed.pdf"
    config = SignatureConfig(stamp_date=False)
    apply(
        flattened_contract,
        executed,
        signature_png=signature_png,
        placements=resolve_placements(flattened_contract, config),
        config=config,
        signed_on=dt.date(2026, 3, 9),
    )

    with pymupdf.open(str(executed)) as doc:
        assert "03/09/2026" not in doc[3].get_text()


def test_multi_page_stamping(tmp_path: Path, signature_png: Path) -> None:
    path = tmp_path / "multi.pdf"
    doc = pymupdf.open()
    for _ in range(3):
        page = doc.new_page()
        page.insert_text((60, 700), "Carrier Representative:", fontsize=10)
    doc.save(str(path))
    doc.close()

    executed = tmp_path / "executed.pdf"
    result = apply(
        path,
        executed,
        signature_png=signature_png,
        placements=resolve_placements(path, SignatureConfig()),
    )

    assert result.pages_stamped == [1, 2, 3]
    with pymupdf.open(str(executed)) as out:
        assert all(len(out[i].get_images()) == 1 for i in range(3))


# --------------------------------------------------------------------------
# Carrier fields and read-only
# --------------------------------------------------------------------------


def test_carrier_fields_are_filled(
    fillable_contract: Path, signature_png: Path, tmp_path: Path
) -> None:
    executed = tmp_path / "executed.pdf"
    result = apply(
        fillable_contract,
        executed,
        signature_png=signature_png,
        placements=resolve_placements(fillable_contract, SignatureConfig()),
        carrier_fills={"carrier_name": "Grand One LLC", "carrier_rep_title": "Owner"},
    )

    assert set(result.carrier_fields_filled) == {"carrier_name", "carrier_rep_title"}
    with pymupdf.open(str(executed)) as doc:
        values = {
            w.field_name: w.field_value for page in doc for w in (page.widgets() or [])
        }
    assert values["carrier_name"] == "Grand One LLC"
    assert values["carrier_rep_title"] == "Owner"


def test_driver_answers_are_not_altered(
    fillable_contract: Path, signature_png: Path, tmp_path: Path
) -> None:
    """The app fills carrier-side fields only. Driver answers are their
    statements, and editing them after signing invalidates the document."""

    with pymupdf.open(str(fillable_contract)) as doc:
        before = {
            w.field_name: w.field_value for page in doc for w in (page.widgets() or [])
        }

    executed = tmp_path / "executed.pdf"
    apply(
        fillable_contract,
        executed,
        signature_png=signature_png,
        placements=resolve_placements(fillable_contract, SignatureConfig()),
        carrier_fills={"carrier_name": "Grand One LLC"},
    )

    with pymupdf.open(str(executed)) as doc:
        after = {
            w.field_name: w.field_value for page in doc for w in (page.widgets() or [])
        }

    for name, value in before.items():
        if name.startswith("carrier_"):
            continue
        assert after[name] == value, f"{name} was altered"


def test_every_widget_is_read_only_afterwards(
    fillable_contract: Path, signature_png: Path, tmp_path: Path
) -> None:
    """The executed file must not be alterable by reopening it."""

    executed = tmp_path / "executed.pdf"
    apply(
        fillable_contract,
        executed,
        signature_png=signature_png,
        placements=resolve_placements(fillable_contract, SignatureConfig()),
    )

    with pymupdf.open(str(executed)) as doc:
        widgets = [w for page in doc for w in (page.widgets() or [])]
        assert widgets, "fixture should still have widgets"
        assert all(w.field_flags & 1 for w in widgets)


def test_stamping_a_flattened_pdf_needs_no_widgets(
    flattened_contract: Path, signature_png: Path, tmp_path: Path
) -> None:
    executed = tmp_path / "executed.pdf"
    result = apply(
        flattened_contract,
        executed,
        signature_png=signature_png,
        placements=resolve_placements(flattened_contract, SignatureConfig()),
        carrier_fills={"carrier_name": "Grand One LLC"},
    )

    assert result.carrier_fields_filled == []
    assert result.pages_stamped == [4]


# --------------------------------------------------------------------------
# Preview
# --------------------------------------------------------------------------


def test_preview_returns_png_bytes(flattened_contract: Path) -> None:
    data = preview_page(flattened_contract, 1)
    assert data.startswith(b"\x89PNG\r\n\x1a\n")


def test_preview_with_boxes_differs_from_without(flattened_contract: Path) -> None:
    placements = resolve_placements(flattened_contract, SignatureConfig())
    plain = preview_page(flattened_contract, 4)
    boxed = preview_page(flattened_contract, 4, boxes=True, placements=placements)

    assert plain != boxed


def test_preview_boxes_only_draw_on_their_own_page(flattened_contract: Path) -> None:
    placements = [Placement(page=4, x=60, y=600, width=150, height=32, how="anchor")]
    plain = preview_page(flattened_contract, 1)
    boxed = preview_page(flattened_contract, 1, boxes=True, placements=placements)

    assert plain == boxed


def test_preview_does_not_modify_the_file(flattened_contract: Path) -> None:
    before = flattened_contract.read_bytes()
    placements = resolve_placements(flattened_contract, SignatureConfig())
    preview_page(flattened_contract, 4, boxes=True, placements=placements)

    assert flattened_contract.read_bytes() == before


@pytest.mark.parametrize("page_no", [0, 5, -1])
def test_preview_rejects_a_page_out_of_range(
    flattened_contract: Path, page_no: int
) -> None:
    with pytest.raises(IndexError):
        preview_page(flattened_contract, page_no)
