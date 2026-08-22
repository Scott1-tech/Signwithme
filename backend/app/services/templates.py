"""Learn where the signature and date go, from a contract already signed.

The reviewer has a stack of contracts that were completed correctly. Rather
than describing coordinates by hand, they hand one of those to the app: it
finds the signature images and the dates already sitting on the page and
records where they are. Every later contract of the same kind is then
stamped in exactly those places.

Detection is deterministic and reviewable. Nothing here guesses at meaning —
it reports *what is on the page and where*, and the reviewer confirms it in
the UI before the template is used. A wrong detection is switched off rather
than silently applied.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from app.services.rules import parse_date

#: A signature is a modest block of ink. Anything outside this is a logo,
#: a scanned page, a rule line, or a background.
MIN_SIGNATURE_WIDTH = 25.0
MAX_SIGNATURE_WIDTH = 420.0
MIN_SIGNATURE_HEIGHT = 8.0
MAX_SIGNATURE_HEIGHT = 220.0

#: An image covering this much of the page is the page, not a signature.
MAX_PAGE_FRACTION = 0.35

#: How far left of a mark to look for a label that explains it.
LABEL_REACH = 260.0

#: A signature line is as often printed *under* its caption as beside it,
#: so the line just above counts as a label too.
LABEL_ABOVE = 46.0
LABEL_SIDE_SLACK = 150.0

#: Dates are at most three words: "March 1, 2025".
MAX_DATE_WORDS = 3

#: A contract is full of dates that belong to the driver — date of birth,
#: licence expiry, employment spans. Those must never become template marks:
#: stamping the carrier's date over a driver's date of birth would alter
#: what the driver attested to. So a date only counts when it sits in the
#: signature's own band, which is where the counter-signature date goes.
DATE_BAND_PADDING = 20.0
DATE_REACH_LEFT = 40.0
DATE_REACH_RIGHT = 400.0

_DATE_HINT = re.compile(r"\d")


@dataclass
class DetectedMark:
    """One thing found on the source contract, with where it sits."""

    kind: str  # "signature" or "date"
    page: int  # 1-based
    x: float
    y: float
    width: float
    height: float
    detected_as: str  # "image" or "date_text"
    sample_text: str = ""

    @property
    def area(self) -> float:
        return self.width * self.height


@dataclass
class AnalysisResult:
    page_count: int
    page_width: float
    page_height: float
    marks: list[DetectedMark]

    @property
    def signatures(self) -> list[DetectedMark]:
        return [m for m in self.marks if m.kind == "signature"]

    @property
    def dates(self) -> list[DetectedMark]:
        return [m for m in self.marks if m.kind == "date"]


# --------------------------------------------------------------------------
# Labels
# --------------------------------------------------------------------------


def _nearby_label(
    words: list[tuple], x: float, y: float, width: float, height: float
) -> str:
    """The printed text that explains a mark, for the reviewer's benefit.

    A signature block almost always carries something like "Carrier
    Representative" — sometimes to its left on the same line, sometimes
    printed on the line above it. Both are checked, nearest first.
    """

    middle = y + height / 2
    beside = [
        word
        for word in words
        if abs((word[1] + word[3]) / 2 - middle) <= max(height, 14.0)
        and word[2] <= x + 2
        and x - word[2] <= LABEL_REACH
    ]
    if beside:
        beside.sort(key=lambda word: word[0])
        return " ".join(word[4] for word in beside[-6:]).strip()[:120]

    # Nothing beside it, so look at the line above.
    left = x - LABEL_SIDE_SLACK
    right = x + width + LABEL_SIDE_SLACK
    above = [
        word
        for word in words
        if -2 <= y - word[3] <= LABEL_ABOVE and word[2] >= left and word[0] <= right
    ]
    if not above:
        return ""

    # Only the closest line up, not everything stacked above the mark.
    nearest = min(y - word[3] for word in above)
    line = [word for word in above if (y - word[3]) - nearest <= 4]
    line.sort(key=lambda word: word[0])
    return " ".join(word[4] for word in line[:8]).strip()[:120]


# --------------------------------------------------------------------------
# Signatures
# --------------------------------------------------------------------------


def _plausible_signature(rect: pymupdf.Rect, page_area: float) -> bool:
    width, height = rect.width, rect.height
    if width < MIN_SIGNATURE_WIDTH or width > MAX_SIGNATURE_WIDTH:
        return False
    if height < MIN_SIGNATURE_HEIGHT or height > MAX_SIGNATURE_HEIGHT:
        return False
    if page_area and (width * height) / page_area > MAX_PAGE_FRACTION:
        return False
    return True


def _signature_marks(page, page_no: int, words: list[tuple]) -> list[DetectedMark]:
    page_area = page.rect.width * page.rect.height
    marks: list[DetectedMark] = []
    seen: set[tuple[int, int, int, int]] = set()

    for info in page.get_image_info() or []:
        bbox = info.get("bbox")
        if not bbox:
            continue
        rect = pymupdf.Rect(bbox)
        if not _plausible_signature(rect, page_area):
            continue

        # The same image placed twice at the same spot is one mark.
        key = (round(rect.x0), round(rect.y0), round(rect.x1), round(rect.y1))
        if key in seen:
            continue
        seen.add(key)

        marks.append(
            DetectedMark(
                kind="signature",
                page=page_no,
                x=rect.x0,
                y=rect.y0,
                width=rect.width,
                height=rect.height,
                detected_as="image",
                sample_text=_nearby_label(
                    words, rect.x0, rect.y0, rect.width, rect.height
                ),
            )
        )

    return marks


# --------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------


def _date_marks(page_no: int, words: list[tuple]) -> list[DetectedMark]:
    """Find every readable date, longest phrase first.

    Longest first matters: "March 1, 2025" must be taken as one date rather
    than leaving "2025" behind as a second, wrong one.
    """

    marks: list[DetectedMark] = []
    claimed: set[int] = set()

    for span in range(MAX_DATE_WORDS, 0, -1):
        for start in range(len(words) - span + 1):
            indices = range(start, start + span)
            if any(index in claimed for index in indices):
                continue

            chunk = [words[index] for index in indices]
            # Words of a single date sit on one line.
            if len({word[5:8][1] for word in chunk}) > 1:
                continue

            text = " ".join(word[4] for word in chunk).strip()
            if not _DATE_HINT.search(text):
                continue
            if parse_date(text.strip(" ,.")) is None:
                continue

            x0 = min(word[0] for word in chunk)
            y0 = min(word[1] for word in chunk)
            x1 = max(word[2] for word in chunk)
            y1 = max(word[3] for word in chunk)

            for index in indices:
                claimed.add(index)

            marks.append(
                DetectedMark(
                    kind="date",
                    page=page_no,
                    x=x0,
                    y=y0,
                    width=x1 - x0,
                    height=y1 - y0,
                    detected_as="date_text",
                    sample_text=text[:120],
                )
            )

    return marks


# --------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------


def _beside_a_signature(date: DetectedMark, signatures: list[DetectedMark]) -> bool:
    """Is this date in the band of a signature on the same page?"""

    middle = date.y + date.height / 2
    for signature in signatures:
        top = signature.y - DATE_BAND_PADDING
        bottom = signature.y + signature.height + DATE_BAND_PADDING
        if not top <= middle <= bottom:
            continue
        if date.x < signature.x - DATE_REACH_LEFT:
            continue
        if date.x > signature.x + signature.width + DATE_REACH_RIGHT:
            continue
        return True
    return False


def analyze(
    path: str | Path,
    *,
    include_dates: bool = True,
    dates_beside_signatures: bool = True,
) -> AnalysisResult:
    """Report every signature and date found on an already-signed contract.

    By default only dates sitting beside a signature are reported, because
    every other date on the page belongs to the driver. Pass
    ``dates_beside_signatures=False`` to see them all — useful when the
    counter-signature date is printed somewhere unusual and the reviewer
    wants to pick it out by hand.
    """

    marks: list[DetectedMark] = []

    with pymupdf.open(str(path)) as doc:
        page_count = doc.page_count
        first = doc[0].rect if page_count else pymupdf.Rect(0, 0, 612, 792)

        for page_no, page in enumerate(doc, start=1):
            words = page.get_text("words") or []
            signatures = _signature_marks(page, page_no, words)
            marks.extend(signatures)

            if include_dates:
                dates = _date_marks(page_no, words)
                if dates_beside_signatures:
                    dates = [d for d in dates if _beside_a_signature(d, signatures)]
                marks.extend(dates)

    marks.sort(key=lambda mark: (mark.page, mark.y, mark.x))

    return AnalysisResult(
        page_count=page_count,
        page_width=first.width,
        page_height=first.height,
        marks=marks,
    )
