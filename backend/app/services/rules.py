"""The validation engine. This module is the product.

Every check is a deterministic rule with a stable ``rule_id``, so reporting
can count how often a given problem shows up. Never rename an id — other
things count them.

Messages are shown to the reviewer verbatim and are pasted into a text
message to the driver, which sets two requirements:

* Write plain English someone can act on. ``CDL expired on 03/01/2025``,
  never ``validation error in field 7``.
* Never put a Social Security number in a message. The SSN rules describe
  the problem without echoing the number.

**One documented deviation.** Specification section 8 gives an "unreadable"
rule to every date on the form — ``cdl.issue_unreadable``,
``dob.unreadable``, ``signature.date_unreadable``,
``employment.date_unreadable`` — except the CDL expiry date. Since an
unparseable date must be an error rather than a silent skip, and reusing
``cdl.issue_unreadable`` would mis-attribute the count, this module adds
``cdl.expiry_unreadable``. It is listed in ``ADDED_RULE_IDS`` so the
addition stays visible.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Iterable, Sequence

from app.services.config_store import FieldSpec
from app.services.extract import ExtractedValue

ERROR = "error"
WARNING = "warning"

#: Exactly the rules in specification section 8.
SPEC_RULE_IDS = frozenset(
    {
        "field.missing",
        "field.blank",
        "ssn.length",
        "ssn.invalid",
        "cdl.state_invalid",
        "cdl.number_format",
        "cdl.issue_unreadable",
        "cdl.issue_future",
        "cdl.expired",
        "cdl.expiring_soon",
        "cdl.expiry_before_issue",
        "dob.unreadable",
        "dob.under_21",
        "dob.implausible",
        "phone.length",
        "email.format",
        "signature.driver_missing",
        "signature.date_unreadable",
        "signature.date_future",
        "employment.none",
        "employment.company_missing",
        "employment.date_unreadable",
        "employment.reversed",
        "employment.gap",
        "employment.recent_gap",
        "employment.under_3_years",
        "employment.under_10_years",
    }
)

#: Rules this module adds beyond the specification. See the module docstring.
ADDED_RULE_IDS = frozenset({"cdl.expiry_unreadable"})

ALL_RULE_IDS = SPEC_RULE_IDS | ADDED_RULE_IDS

#: Accepted date formats, tried in order.
DATE_FORMATS = (
    "%m/%d/%Y",
    "%m-%d-%Y",
    "%Y-%m-%d",
    "%m/%d/%y",
    "%d %b %Y",
    "%B %d, %Y",
)

#: An end date of "Present" means the driver still works there.
ONGOING = {"present", "current", "currently", "to date", "ongoing", "now"}

US_STATES = frozenset(
    """AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN
    MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV
    WI WY""".split()
)

#: Deliberately basic — this checks a typo, not deliverability.
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")

CDL_NUMBER_PATTERN = re.compile(r"^[A-Za-z0-9]{4,20}$")

_EMPLOYMENT_KEY = re.compile(r"^emp(\d+)_(company|from|to)$")

#: Thresholds, named so the boundaries are readable in the rules below.
GAP_DAYS = 30
EXPIRING_SOON_DAYS = 60
MIN_AGE = 21
IMPLAUSIBLE_AGE = 90
REQUIRED_HISTORY_YEARS = 3
CDL_HISTORY_YEARS = 10
DAYS_PER_YEAR = 365.25


@dataclass(frozen=True)
class Flag:
    rule_id: str
    field_key: str
    page: int | None
    severity: str
    message: str


# --------------------------------------------------------------------------
# Parsing helpers
# --------------------------------------------------------------------------


def parse_date(text: str | None) -> dt.date | None:
    """Parse a date in any accepted format, or return None.

    Returning None is never a pass. Every caller turns it into an error.
    """

    if not text:
        return None
    cleaned = " ".join(text.split())
    if not cleaned:
        return None
    for fmt in DATE_FORMATS:
        try:
            return dt.datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def is_ongoing(text: str | None) -> bool:
    return bool(text) and text.strip().lower().rstrip(".") in ONGOING


def digits(text: str | None) -> str:
    return "".join(character for character in (text or "") if character.isdigit())


def age_on(born: dt.date, reference: dt.date) -> int:
    """Whole years old on the reference date."""

    had_birthday = (reference.month, reference.day) >= (born.month, born.day)
    return reference.year - born.year - (0 if had_birthday else 1)


def _years_between(earlier: dt.date, later: dt.date) -> float:
    return (later - earlier).days / DAYS_PER_YEAR


def _fmt_years(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


# --------------------------------------------------------------------------
# Field index
# --------------------------------------------------------------------------


class _Fields:
    """Lookup over what was extracted, plus what the field map requires."""

    def __init__(
        self,
        fields: Iterable[ExtractedValue],
        specs: Iterable[FieldSpec],
    ) -> None:
        self._values = {f.field_key: f for f in fields}
        self._specs = {s.field_key: s for s in specs}

    @property
    def keys(self) -> list[str]:
        return list(self._specs)

    def mapped(self, key: str) -> bool:
        """Is this field part of the field map at all?"""

        return key in self._specs

    def found(self, key: str) -> bool:
        entry = self._values.get(key)
        return bool(entry and entry.found)

    def raw(self, key: str) -> str:
        entry = self._values.get(key)
        return (entry.value or "").strip() if entry else ""

    def filled(self, key: str) -> bool:
        """Found, and with something in it."""

        return self.found(key) and bool(self.raw(key))

    def page(self, key: str) -> int | None:
        entry = self._values.get(key)
        return entry.page if entry else None

    def label(self, key: str) -> str:
        spec = self._specs.get(key)
        if spec:
            return spec.label
        entry = self._values.get(key)
        return entry.label if entry else key

    def required(self, key: str) -> bool:
        spec = self._specs.get(key)
        return bool(spec and spec.required)


# --------------------------------------------------------------------------
# The rules
# --------------------------------------------------------------------------


def validate(
    fields: Iterable[ExtractedValue],
    specs: Iterable[FieldSpec],
    *,
    today: dt.date | None = None,
) -> list[Flag]:
    """Check one contract and return every problem found."""

    now = today or dt.date.today()
    index = _Fields(fields, specs)
    flags: list[Flag] = []

    _check_presence(index, flags)
    _check_ssn(index, flags)
    _check_cdl(index, flags, now)
    _check_dob(index, flags, now)
    _check_phone(index, flags)
    _check_email(index, flags)
    _check_signature(index, flags, now)
    _check_employment(index, flags, now)

    severity_rank = {ERROR: 0, WARNING: 1}
    flags.sort(
        key=lambda f: (
            severity_rank.get(f.severity, 2),
            f.page if f.page is not None else 10**6,
            f.field_key,
            f.rule_id,
        )
    )
    return flags


def _flag(
    flags: list[Flag],
    index: _Fields,
    rule_id: str,
    field_key: str,
    severity: str,
    message: str,
) -> None:
    flags.append(
        Flag(
            rule_id=rule_id,
            field_key=field_key,
            page=index.page(field_key),
            severity=severity,
            message=message,
        )
    )


# --- presence -------------------------------------------------------------

#: Fields whose emptiness is reported by a rule of their own, so the generic
#: blank check stays quiet and the reviewer sees one flag, not two.
_OWN_BLANK_RULE = {"driver_signature"}


def _check_presence(index: _Fields, flags: list[Flag]) -> None:
    for key in index.keys:
        if not index.required(key):
            continue
        if not index.found(key):
            _flag(
                flags,
                index,
                "field.missing",
                key,
                ERROR,
                f"{index.label(key)} could not be found in the contract.",
            )
        elif not index.raw(key) and key not in _OWN_BLANK_RULE:
            _flag(
                flags,
                index,
                "field.blank",
                key,
                ERROR,
                f"{index.label(key)} is blank.",
            )


# --- SSN ------------------------------------------------------------------


def _check_ssn(index: _Fields, flags: list[Flag]) -> None:
    if not index.filled("ssn"):
        return

    number = digits(index.raw("ssn"))
    if len(number) != 9:
        _flag(
            flags,
            index,
            "ssn.length",
            "ssn",
            ERROR,
            "Social Security Number must be nine digits; "
            f"{len(number)} were entered.",
        )
        return

    area, group, serial = number[:3], number[3:5], number[5:]
    reason: str | None = None
    if area == "000":
        reason = "the first three digits cannot be 000"
    elif area == "666":
        reason = "the first three digits cannot be 666"
    elif int(area) >= 900:
        reason = "the first three digits cannot be 900 or above"
    elif group == "00":
        reason = "the middle two digits cannot be 00"
    elif serial == "0000":
        reason = "the last four digits cannot be 0000"

    if reason:
        _flag(
            flags,
            index,
            "ssn.invalid",
            "ssn",
            ERROR,
            f"Social Security Number is not a valid number — {reason}.",
        )


# --- CDL ------------------------------------------------------------------


def _check_cdl(index: _Fields, flags: list[Flag], today: dt.date) -> None:
    if index.filled("cdl_state"):
        state = index.raw("cdl_state").strip().upper()
        if state not in US_STATES:
            _flag(
                flags,
                index,
                "cdl.state_invalid",
                "cdl_state",
                ERROR,
                f"CDL state “{index.raw('cdl_state')}” is not a US "
                "state or DC code.",
            )

    if index.filled("cdl_number"):
        compact = index.raw("cdl_number").replace(" ", "").replace("-", "")
        if not CDL_NUMBER_PATTERN.match(compact):
            _flag(
                flags,
                index,
                "cdl.number_format",
                "cdl_number",
                ERROR,
                f"CDL number “{index.raw('cdl_number')}” does not "
                "look like a licence number.",
            )

    issued: dt.date | None = None
    if index.filled("cdl_issued"):
        issued = parse_date(index.raw("cdl_issued"))
        if issued is None:
            _flag(
                flags,
                index,
                "cdl.issue_unreadable",
                "cdl_issued",
                ERROR,
                f"CDL issue date could not be read: “{index.raw('cdl_issued')}”.",
            )
        elif issued > today:
            _flag(
                flags,
                index,
                "cdl.issue_future",
                "cdl_issued",
                ERROR,
                f"CDL issue date {issued.strftime('%m/%d/%Y')} is in the future.",
            )

    expires: dt.date | None = None
    if index.filled("cdl_expires"):
        expires = parse_date(index.raw("cdl_expires"))
        if expires is None:
            _flag(
                flags,
                index,
                "cdl.expiry_unreadable",
                "cdl_expires",
                ERROR,
                "CDL expiration date could not be read: "
                f"“{index.raw('cdl_expires')}”.",
            )
        elif expires <= today:
            _flag(
                flags,
                index,
                "cdl.expired",
                "cdl_expires",
                ERROR,
                f"CDL expired on {expires.strftime('%m/%d/%Y')}.",
            )
        elif (expires - today).days <= EXPIRING_SOON_DAYS:
            remaining = (expires - today).days
            _flag(
                flags,
                index,
                "cdl.expiring_soon",
                "cdl_expires",
                WARNING,
                f"CDL expires on {expires.strftime('%m/%d/%Y')}, "
                f"in {remaining} days.",
            )

    if issued and expires and expires < issued:
        _flag(
            flags,
            index,
            "cdl.expiry_before_issue",
            "cdl_expires",
            ERROR,
            f"CDL expiration {expires.strftime('%m/%d/%Y')} is before the "
            f"issue date {issued.strftime('%m/%d/%Y')}.",
        )


# --- date of birth --------------------------------------------------------


def _check_dob(index: _Fields, flags: list[Flag], today: dt.date) -> None:
    if not index.filled("dob"):
        return

    born = parse_date(index.raw("dob"))
    if born is None:
        _flag(
            flags,
            index,
            "dob.unreadable",
            "dob",
            ERROR,
            f"Date of birth could not be read: “{index.raw('dob')}”.",
        )
        return

    age = age_on(born, today)
    if age < MIN_AGE:
        _flag(
            flags,
            index,
            "dob.under_21",
            "dob",
            ERROR,
            f"Driver is {age}. A driver must be 21 to operate in interstate "
            "commerce (49 CFR 391.11).",
        )
    elif age > IMPLAUSIBLE_AGE:
        _flag(
            flags,
            index,
            "dob.implausible",
            "dob",
            WARNING,
            f"Date of birth {born.strftime('%m/%d/%Y')} makes the driver "
            f"{age} years old. Check it was entered correctly.",
        )


# --- phone and email ------------------------------------------------------


def _check_phone(index: _Fields, flags: list[Flag]) -> None:
    if not index.filled("phone"):
        return
    count = len(digits(index.raw("phone")))
    if count not in (10, 11):
        _flag(
            flags,
            index,
            "phone.length",
            "phone",
            ERROR,
            f"Phone number must be 10 or 11 digits; {count} were entered.",
        )


def _check_email(index: _Fields, flags: list[Flag]) -> None:
    if not index.filled("email"):
        return
    value = index.raw("email")
    if not EMAIL_PATTERN.match(value):
        _flag(
            flags,
            index,
            "email.format",
            "email",
            ERROR,
            f"Email address “{value}” is not a valid address.",
        )


# --- signature ------------------------------------------------------------


def _check_signature(index: _Fields, flags: list[Flag], today: dt.date) -> None:
    if index.found("driver_signature") and not index.raw("driver_signature"):
        _flag(
            flags,
            index,
            "signature.driver_missing",
            "driver_signature",
            ERROR,
            "The driver signature block is empty.",
        )

    if not index.filled("signature_date"):
        return

    signed = parse_date(index.raw("signature_date"))
    if signed is None:
        _flag(
            flags,
            index,
            "signature.date_unreadable",
            "signature_date",
            ERROR,
            "The signature date could not be read: "
            f"“{index.raw('signature_date')}”.",
        )
    elif signed > today:
        _flag(
            flags,
            index,
            "signature.date_future",
            "signature_date",
            ERROR,
            f"The contract is dated {signed.strftime('%m/%d/%Y')}, "
            "which is in the future.",
        )


# --- employment history ---------------------------------------------------


@dataclass
class _Job:
    number: int
    company: str
    start: dt.date | None
    end: dt.date | None
    #: True when the end date reads "Present".
    ongoing: bool

    @property
    def name(self) -> str:
        return self.company or f"employer {self.number}"


def _employment_numbers(index: _Fields) -> list[int]:
    numbers = set()
    for key in index.keys:
        match = _EMPLOYMENT_KEY.match(key)
        if match:
            numbers.add(int(match.group(1)))
    return sorted(numbers)


def _check_employment(index: _Fields, flags: list[Flag], today: dt.date) -> None:
    numbers = _employment_numbers(index)
    if not numbers:
        # This contract type has no employment section to check.
        return

    declared: list[_Job] = []
    anything_entered = False

    for number in numbers:
        company_key = f"emp{number}_company"
        from_key = f"emp{number}_from"
        to_key = f"emp{number}_to"

        company = index.raw(company_key)
        from_raw = index.raw(from_key)
        to_raw = index.raw(to_key)

        if not (company or from_raw or to_raw):
            continue
        anything_entered = True

        start = parse_date(from_raw)
        if start is None:
            _flag(
                flags,
                index,
                "employment.date_unreadable",
                from_key,
                ERROR,
                f"Employer {number} start date "
                + (
                    "is blank."
                    if not from_raw
                    else f"could not be read: “{from_raw}”."
                ),
            )

        ongoing = is_ongoing(to_raw)
        end = today if ongoing else parse_date(to_raw)
        if end is None:
            _flag(
                flags,
                index,
                "employment.date_unreadable",
                to_key,
                ERROR,
                f"Employer {number} end date "
                + (
                    "is blank."
                    if not to_raw
                    else f"could not be read: “{to_raw}”."
                ),
            )

        if start and end and not company:
            _flag(
                flags,
                index,
                "employment.company_missing",
                company_key,
                ERROR,
                f"Employer {number} has dates but no company name.",
            )

        if start and end and end < start:
            _flag(
                flags,
                index,
                "employment.reversed",
                to_key,
                ERROR,
                f"Employer {number} ends {end.strftime('%m/%d/%Y')}, before "
                f"it starts on {start.strftime('%m/%d/%Y')}.",
            )

        declared.append(_Job(number, company, start, end, ongoing))

    if not anything_entered:
        page = index.page(f"emp{numbers[0]}_company")
        flags.append(
            Flag(
                rule_id="employment.none",
                field_key=f"emp{numbers[0]}_company",
                page=page,
                severity=ERROR,
                message="No employment history could be read from the "
                "contract. Three years are required (49 CFR 391.21).",
            )
        )
        return

    spans = [job for job in declared if job.start and job.end and job.end >= job.start]
    if not spans:
        # Every block was unreadable; those flags are already raised.
        return

    spans.sort(key=lambda job: job.start)  # type: ignore[arg-type,return-value]

    # Gaps between consecutive jobs. Track the furthest end seen so far so
    # that overlapping jobs do not read as a gap.
    previous = spans[0]
    running_end = spans[0].end
    assert running_end is not None
    for job in spans[1:]:
        assert job.start is not None and job.end is not None
        gap = (job.start - running_end).days
        if gap > GAP_DAYS:
            _flag(
                flags,
                index,
                "employment.gap",
                f"emp{job.number}_from",
                ERROR,
                f"{gap}-day gap between {previous.name} ending "
                f"{running_end.strftime('%m/%d/%Y')} and {job.name} starting "
                f"{job.start.strftime('%m/%d/%Y')}.",
            )
        if job.end > running_end:
            running_end = job.end
            previous = job

    latest = max(spans, key=lambda job: job.end)  # type: ignore[arg-type,return-value]
    assert latest.end is not None
    recent_gap = (today - latest.end).days
    if recent_gap > GAP_DAYS:
        _flag(
            flags,
            index,
            "employment.recent_gap",
            f"emp{latest.number}_to",
            ERROR,
            f"{recent_gap}-day gap between the most recent job ending "
            f"{latest.end.strftime('%m/%d/%Y')} and today.",
        )

    earliest = min(spans, key=lambda job: job.start)  # type: ignore[arg-type,return-value]
    assert earliest.start is not None
    reach = _years_between(earliest.start, today)
    reach_key = f"emp{earliest.number}_from"
    if reach < REQUIRED_HISTORY_YEARS:
        _flag(
            flags,
            index,
            "employment.under_3_years",
            reach_key,
            ERROR,
            f"Employment history reaches back {_fmt_years(reach)} years. "
            "Three years are required (49 CFR 391.21).",
        )
    elif reach < CDL_HISTORY_YEARS:
        # Graduated pair: under three years is already under ten, and firing
        # both would report one problem twice.
        _flag(
            flags,
            index,
            "employment.under_10_years",
            reach_key,
            WARNING,
            f"Employment history reaches back {_fmt_years(reach)} years. Ten "
            "years are required where the driver held a CDL (49 CFR 391.21).",
        )
