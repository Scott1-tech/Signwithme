"""Carrier signature stamping and page rendering.

Placement resolves two ways. **Anchor** searches each page for a phrase such
as "Carrier Representative" and offsets from the first hit, which survives
the page shifts that happen when a contract is revised. **Offset** is a
fixed position expressed as a fraction of page width and height, so letter
and legal both work; it is also the fallback when the anchor is not found.

Stamping never writes over the original upload. The executed file is a new
document, and the original is retained beside it.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import pymupdf

from app.services.config_store import SignatureConfig

#: PyMuPDF exposes the AcroForm read-only bit; fall back to the PDF spec
#: value if a future version renames the constant.
READ_ONLY_FLAG = getattr(pymupdf, "PDF_FIELD_IS_READ_ONLY", 1)

PREVIEW_DPI = 110


@dataclass(frozen=True)
class Placement:
    """Where one signature lands. Page numbers are 1-based."""

    page: int
    x: float
    y: float
    width: float
    height: float
    #: "anchor" or "offset", so the reviewer can see how it was decided.
    how: str

    @property
    def rect(self) -> pymupdf.Rect:
        return pymupdf.Rect(self.x, self.y, self.x + self.width, self.y + self.height)


@dataclass
class StampResult:
    output_path: Path
    pages_stamped: list[int] = field(default_factory=list)
    carrier_fields_filled: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# Placement
# --------------------------------------------------------------------------


def _resolve_page_number(requested: int, page_count: int) -> int | None:
    """1-based, with negatives counting from the end. -1 is the last page."""

    if requested == 0 or page_count == 0:
        return None
    index = requested if requested > 0 else page_count + requested + 1
    return index if 1 <= index <= page_count else None


def _anchor_placements(doc: pymupdf.Document, config: SignatureConfig) -> list[Placement]:
    placements: list[Placement] = []
    phrase = config.anchor_phrase.strip()
    if not phrase:
        return placements

    for page_index, page in enumerate(doc, start=1):
        hits = page.search_for(phrase)
        if not hits:
            continue
        # Offset from the first hit on the page, per the specification.
        hit = hits[0]
        placements.append(
            Placement(
                page=page_index,
                x=hit.x0 + config.dx,
                y=hit.y1 + config.dy,
                width=config.width,
                height=config.height,
                how="anchor",
            )
        )
        if len(placements) >= config.max_stamps:
            break
    return placements


def _offset_placements(doc: pymupdf.Document, config: SignatureConfig) -> list[Placement]:
    placements: list[Placement] = []
    seen: set[int] = set()

    for requested in config.offset_pages:
        page_number = _resolve_page_number(requested, doc.page_count)
        if page_number is None or page_number in seen:
            continue
        seen.add(page_number)
        page = doc[page_number - 1]
        rect = page.rect
        placements.append(
            Placement(
                page=page_number,
                x=rect.width * config.offset_x_frac,
                y=rect.height * config.offset_y_frac,
                width=config.width,
                height=config.height,
                how="offset",
            )
        )
        if len(placements) >= config.max_stamps:
            break
    return placements


def resolve_placements(
    path: str | Path, config: SignatureConfig | None = None
) -> list[Placement]:
    """Work out where the signature goes, without writing anything."""

    settings = config or SignatureConfig()
    with pymupdf.open(str(path)) as doc:
        if settings.mode == "anchor":
            placements = _anchor_placements(doc, settings)
            if not placements and settings.fallback_to_offset:
                placements = _offset_placements(doc, settings)
            return placements
        return _offset_placements(doc, settings)


# --------------------------------------------------------------------------
# Stamping
# --------------------------------------------------------------------------


def apply(
    source: str | Path,
    destination: str | Path,
    *,
    signature_png: str | Path,
    placements: Sequence[Placement],
    config: SignatureConfig | None = None,
    signed_on: dt.date | None = None,
    carrier_fills: dict[str, str] | None = None,
) -> StampResult:
    """Stamp the signature and write a new executed PDF.

    Fills carrier-side AcroForm fields from config, sets every widget
    read-only so the executed file cannot be altered by reopening it, and
    saves to ``destination``. The driver's own answers are never touched.
    """

    source_path = Path(source).resolve()
    destination_path = Path(destination).resolve()
    if source_path == destination_path:
        raise ValueError("Stamping must not write over the original upload")
    if not placements:
        raise ValueError("No signature placements resolved")

    settings = config or SignatureConfig()
    date_text = (signed_on or dt.date.today()).strftime(settings.date_format)
    result = StampResult(output_path=destination_path)

    doc = pymupdf.open(str(source_path))
    try:
        for placement in placements:
            if not 1 <= placement.page <= doc.page_count:
                continue
            page = doc[placement.page - 1]
            page.insert_image(
                placement.rect,
                filename=str(signature_png),
                keep_proportion=True,
                overlay=True,
            )
            if settings.stamp_date:
                page.insert_text(
                    (
                        placement.x + settings.date_dx,
                        placement.y + settings.date_dy,
                    ),
                    date_text,
                    fontsize=settings.date_font_size,
                    fontname="helv",
                )
            result.pages_stamped.append(placement.page)

        fills = carrier_fills or {}
        for page in doc:
            for widget in page.widgets() or []:
                name = (widget.field_name or "").strip()
                if name in fills:
                    widget.field_value = fills[name]
                    result.carrier_fields_filled.append(name)
                # Read-only last, so the fill above still takes.
                widget.field_flags = int(widget.field_flags or 0) | READ_ONLY_FLAG
                widget.update()

        destination_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(destination_path), deflate=True)
    finally:
        doc.close()

    return result


# --------------------------------------------------------------------------
# Preview
# --------------------------------------------------------------------------


def preview_page(
    path: str | Path,
    page_no: int,
    *,
    boxes: bool = False,
    placements: Sequence[Placement] | None = None,
    dpi: int = PREVIEW_DPI,
) -> bytes:
    """Render one page to PNG bytes, optionally with placement boxes drawn.

    The frontend shows these instead of running a PDF viewer in the browser.
    Nothing is saved: the boxes are drawn on the in-memory copy only.
    """

    doc = pymupdf.open(str(path))
    try:
        if not 1 <= page_no <= doc.page_count:
            raise IndexError(
                f"Page {page_no} is out of range; the document has "
                f"{doc.page_count} pages"
            )
        page = doc[page_no - 1]

        if boxes:
            for placement in placements or []:
                if placement.page != page_no:
                    continue
                page.draw_rect(
                    placement.rect,
                    color=(0.86, 0.15, 0.15),
                    width=1.2,
                    overlay=True,
                )

        pixmap = page.get_pixmap(dpi=dpi)
        return pixmap.tobytes("png")
    finally:
        doc.close()
