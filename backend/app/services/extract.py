"""Read the driver's answers out of a contract PDF.

Two paths, exact one first.

**Path A — AcroForm.** If the PDF still carries form widgets, read
``field_name`` and ``field_value`` straight off them. No ambiguity.

**Path B — label-anchored text.** Completed DocuSign envelopes are usually
flattened: the answers are painted onto the page and the widgets are gone.
So find the label phrase in the page's words, then collect the words to its
right on the same baseline band.

Path B fills any gaps path A left, and ``source`` records which ran.

A field the extractor cannot locate is never silently dropped. It comes back
with ``found=False`` and the rules engine turns that into an error flag.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

import fitz  # PyMuPDF
import pdfplumber

from app.services.config_store import FieldSpec

#: Words are on the same line if their vertical centres are within this many
#: points. Four points is about half a line at 10pt type.
VERTICAL_TOLERANCE = 4.0

#: While walking right from a label, a gap this wide means we have crossed
#: into the next column and the value has ended.
RUN_GAP = 45.0

#: Characters a form uses to draw a blank: "________", "........".
_FILLER = re.compile(r"^[_.\-–—\s]+$")
_PUNCT = re.compile(r"[^\w\s]")
_WS = re.compile(r"\s+")


# --------------------------------------------------------------------------
# Result types
# --------------------------------------------------------------------------


@dataclass
class ExtractedValue:
    field_key: str
    label: str
    value: str | None
    page: int | None
    found: bool


@dataclass
class ExtractionResult:
    """Everything one pass over a contract produced."""

    values: dict[str, str | None] = field(default_factory=dict)
    pages: dict[str, int | None] = field(default_factory=dict)
    #: "acroform", "text", "acroform+text", or "none".
    source: str = "none"
    page_count: int = 0
    not_found: list[str] = field(default_factory=list)
    fields: list[ExtractedValue] = field(default_factory=list)

    def value(self, field_key: str) -> str | None:
        return self.values.get(field_key)

    def page(self, field_key: str) -> int | None:
        return self.pages.get(field_key)


@dataclass
class ProbeWidget:
    page: int
    name: str
    type: str
    #: Whether the widget holds a value. The value itself is withheld: a
    #: probe runs against a real contract and those carry Social Security
    #: numbers. The setup wizard only needs the names.
    has_value: bool


@dataclass
class ProbePage:
    page: int
    text: str


@dataclass
class ProbeResult:
    page_count: int
    has_acroform: bool
    widgets: list[ProbeWidget]
    pages: list[ProbePage]


# --------------------------------------------------------------------------
# Text helpers
# --------------------------------------------------------------------------


def _normalise(text: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace."""

    return _WS.sub(" ", _PUNCT.sub(" ", text.lower())).strip()


def _clean_value(text: str) -> str:
    text = text.strip().strip(":").strip()
    if not text or _FILLER.match(text):
        return ""
    return _WS.sub(" ", text)


# --------------------------------------------------------------------------
# Path A — AcroForm
# --------------------------------------------------------------------------


def _widget_value(widget) -> str:
    raw = widget.field_value
    if raw is None:
        return ""
    if isinstance(raw, bool):
        return "Yes" if raw else ""
    return str(raw).strip()


def extract_acroform(path: str | Path) -> tuple[dict[str, str], dict[str, int]]:
    """Return widget values and 1-based pages, keyed by widget name."""

    values: dict[str, str] = {}
    pages: dict[str, int] = {}
    with fitz.open(str(path)) as doc:
        for page_index, page in enumerate(doc, start=1):
            for widget in page.widgets() or []:
                name = (widget.field_name or "").strip()
                if not name:
                    continue
                value = _widget_value(widget)
                # First occurrence wins, but a later page carrying an actual
                # value beats an earlier empty duplicate of the same field.
                if name not in values or (not values[name] and value):
                    values[name] = value
                    pages[name] = page_index
    return values, pages


def has_widgets(path: str | Path) -> bool:
    with fitz.open(str(path)) as doc:
        for page in doc:
            if page.first_widget is not None:
                return True
    return False


# --------------------------------------------------------------------------
# Path B — label-anchored text
# --------------------------------------------------------------------------


@dataclass
class _Word:
    text: str
    x0: float
    x1: float
    cy: float


def _page_words(page) -> list[_Word]:
    words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
    out = [
        _Word(
            text=w["text"],
            x0=float(w["x0"]),
            x1=float(w["x1"]),
            cy=(float(w["top"]) + float(w["bottom"])) / 2.0,
        )
        for w in words
    ]
    out.sort(key=lambda w: (round(w.cy, 1), w.x0))
    return out


def _lines(words: Sequence[_Word]) -> list[list[_Word]]:
    """Group words into baseline bands."""

    lines: list[list[_Word]] = []
    for word in words:
        for line in lines:
            if abs(line[0].cy - word.cy) <= VERTICAL_TOLERANCE:
                line.append(word)
                break
        else:
            lines.append([word])
    for line in lines:
        line.sort(key=lambda w: w.x0)
    return lines


def _match_anchor(line: Sequence[_Word], anchor_tokens: list[str]) -> int | None:
    """Index just past the anchor phrase in this line, or None.

    Matching is case-insensitive and ignores punctuation, so a form that
    prints ``Date of Birth:`` matches an anchor of ``Date of Birth``.
    """

    normalised = [_normalise(w.text) for w in line]
    span = len(anchor_tokens)
    for start in range(len(line) - span + 1):
        window = [t for t in normalised[start : start + span]]
        if window == anchor_tokens:
            return start + span
    return None


def _collect_right(line: Sequence[_Word], start: int, max_gap: float) -> str:
    """Walk right from the label, gathering the value."""

    if start >= len(line):
        return ""

    anchor_x1 = line[start - 1].x1 if start > 0 else line[0].x0
    parts: list[str] = []
    prev_x1 = anchor_x1

    for word in line[start:]:
        if word.x0 - anchor_x1 > max_gap:
            break
        gap = word.x0 - prev_x1
        if parts and gap > RUN_GAP:
            # Crossed into the next column.
            break
        text = word.text.strip()
        if not parts and text in {":", "-", "–"}:
            prev_x1 = word.x1
            continue
        if len(text) > 1 and text.endswith(":"):
            # A colon-terminated word is the next label on this line, not
            # part of this value. The label's own trailing colon was already
            # consumed by the anchor match.
            break
        if _FILLER.match(text):
            prev_x1 = word.x1
            continue
        parts.append(text)
        prev_x1 = word.x1

    return _clean_value(" ".join(parts))


def extract_text_fields(
    path: str | Path,
    specs: Iterable[FieldSpec],
) -> tuple[dict[str, str], dict[str, int]]:
    """Label-anchored extraction over the whole document.

    Returns values and 1-based pages keyed by canonical field key. A field
    whose label was found but had nothing beside it comes back as an empty
    string — found but blank, which is a different problem from missing.
    """

    wanted = list(specs)
    if not wanted:
        return {}, {}

    values: dict[str, str] = {}
    pages: dict[str, int] = {}

    # Pre-tokenise anchors once rather than per page.
    anchors: dict[str, list[tuple[list[str], float]]] = {}
    for spec in wanted:
        tokens: list[tuple[list[str], float]] = []
        for anchor in spec.anchors:
            normalised = _normalise(anchor).split()
            if normalised:
                tokens.append((normalised, spec.max_gap))
        if tokens:
            anchors[spec.field_key] = tokens

    with pdfplumber.open(str(path)) as pdf:
        for page_index, page in enumerate(pdf.pages, start=1):
            outstanding = [
                spec
                for spec in wanted
                if spec.field_key in anchors and not values.get(spec.field_key)
            ]
            if not outstanding:
                break

            lines = _lines(_page_words(page))
            if not lines:
                continue

            for spec in outstanding:
                if spec.page_hint is not None and spec.page_hint != page_index:
                    continue
                for anchor_tokens, max_gap in anchors[spec.field_key]:
                    for line in lines:
                        cursor = _match_anchor(line, anchor_tokens)
                        if cursor is None:
                            continue
                        value = _collect_right(line, cursor, max_gap)
                        # Record the hit either way: a located label with no
                        # value is "found but blank".
                        if spec.field_key not in values or (
                            not values[spec.field_key] and value
                        ):
                            values[spec.field_key] = value
                            pages[spec.field_key] = page_index
                        if value:
                            break
                    if values.get(spec.field_key):
                        break

    return values, pages


# --------------------------------------------------------------------------
# Merge
# --------------------------------------------------------------------------


def extract(path: str | Path, specs: Iterable[FieldSpec]) -> ExtractionResult:
    """Run both paths and merge, exact one first."""

    wanted = list(specs)
    result = ExtractionResult()

    with fitz.open(str(path)) as doc:
        result.page_count = doc.page_count

    ran_acroform = False
    values: dict[str, str] = {}
    pages: dict[str, int] = {}

    if has_widgets(path):
        ran_acroform = True
        widget_values, widget_pages = extract_acroform(path)
        for spec in wanted:
            name = spec.acroform_name or spec.field_key
            if name in widget_values:
                values[spec.field_key] = widget_values[name]
                page = widget_pages.get(name)
                if page is not None:
                    pages[spec.field_key] = page

    missing_specs = [s for s in wanted if not values.get(s.field_key)]
    ran_text = False
    if missing_specs:
        text_values, text_pages = extract_text_fields(path, missing_specs)
        if text_values:
            ran_text = True
        for key, value in text_values.items():
            if not values.get(key):
                values[key] = value
                if key in text_pages:
                    pages[key] = text_pages[key]

    if ran_acroform and ran_text:
        result.source = "acroform+text"
    elif ran_acroform:
        result.source = "acroform"
    elif ran_text:
        result.source = "text"
    else:
        result.source = "none"

    for spec in wanted:
        found = spec.field_key in values
        value = values.get(spec.field_key)
        result.values[spec.field_key] = value
        result.pages[spec.field_key] = pages.get(spec.field_key)
        if not found:
            result.not_found.append(spec.field_key)
        result.fields.append(
            ExtractedValue(
                field_key=spec.field_key,
                label=spec.label,
                value=value,
                page=pages.get(spec.field_key),
                found=found,
            )
        )

    return result


# --------------------------------------------------------------------------
# Probe — powers the setup wizard
# --------------------------------------------------------------------------


def probe(path: str | Path) -> ProbeResult:
    """Report what a PDF actually contains, so the field map can be fixed.

    Widget *values* are deliberately omitted; see ``ProbeWidget.has_value``.
    """

    widgets: list[ProbeWidget] = []
    with fitz.open(str(path)) as doc:
        page_count = doc.page_count
        for page_index, page in enumerate(doc, start=1):
            for widget in page.widgets() or []:
                name = (widget.field_name or "").strip()
                if not name:
                    continue
                widgets.append(
                    ProbeWidget(
                        page=page_index,
                        name=name,
                        type=widget.field_type_string or "unknown",
                        has_value=bool(_widget_value(widget)),
                    )
                )

    pages: list[ProbePage] = []
    with pdfplumber.open(str(path)) as pdf:
        for page_index, page in enumerate(pdf.pages, start=1):
            pages.append(ProbePage(page=page_index, text=page.extract_text() or ""))

    return ProbeResult(
        page_count=page_count,
        has_acroform=bool(widgets),
        widgets=widgets,
        pages=pages,
    )
