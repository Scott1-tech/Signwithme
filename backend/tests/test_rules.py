"""The rules engine is the product, so it gets the coverage.

Every ``rule_id`` in specification section 8 has a case that fires and a case
that does not, plus the boundaries that decide real contracts: a CDL expiring
exactly today, a driver turning 21 today, employment gaps of exactly 30 and
exactly 31 days.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.services.config_store import FieldSpec, default_field_specs
from app.services.extract import ExtractedValue
from app.services.rules import (
    ADDED_RULE_IDS,
    ALL_RULE_IDS,
    SPEC_RULE_IDS,
    Flag,
    parse_date,
    validate,
)
from tests.conftest import PAGE_OF, clean_values, days, us, years

#: Marks a field the extractor could not locate at all, as opposed to one it
#: found sitting empty. The two are different problems.
MISSING = object()

SPECS = default_field_specs()


def build_fields(overrides: dict[str, object]) -> list[ExtractedValue]:
    data = clean_values()
    out: list[ExtractedValue] = []
    for spec in SPECS:
        key = spec.field_key
        value = overrides.get(key, data.get(key, ""))
        if value is MISSING:
            out.append(ExtractedValue(key, spec.label, None, None, False))
        else:
            out.append(
                ExtractedValue(key, spec.label, str(value), PAGE_OF.get(key), True)
            )
    return out


def run(**overrides: object) -> list[Flag]:
    return validate(build_fields(overrides), SPECS)


def ids(**overrides: object) -> set[str]:
    return {flag.rule_id for flag in run(**overrides)}


def message_for(rule_id: str, **overrides: object) -> str:
    return next(f.message for f in run(**overrides) if f.rule_id == rule_id)


# --------------------------------------------------------------------------
# Baseline
# --------------------------------------------------------------------------


def test_a_clean_contract_raises_nothing() -> None:
    assert run() == []


def test_every_documented_rule_id_is_implemented() -> None:
    """Guards against a rule quietly disappearing in a refactor."""

    assert SPEC_RULE_IDS == {
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


def test_the_only_added_rule_is_the_documented_one() -> None:
    """Section 8 gives every date an "unreadable" rule except the CDL
    expiry. Rather than mis-attribute it to cdl.issue_unreadable or let a
    garbage expiry date pass, the engine adds one id — and only one."""

    assert ADDED_RULE_IDS == {"cdl.expiry_unreadable"}
    assert ALL_RULE_IDS == SPEC_RULE_IDS | ADDED_RULE_IDS


def test_cdl_expiry_unreadable_fires() -> None:
    assert "cdl.expiry_unreadable" in ids(cdl_expires="expires soon")


def test_cdl_expiry_unreadable_does_not_fire() -> None:
    assert "cdl.expiry_unreadable" not in ids()


def test_flags_carry_the_page_number() -> None:
    """The page number is the point of the product."""

    flag = next(f for f in run(cdl_expires=us(days(-1))) if f.rule_id == "cdl.expired")
    assert flag.page == PAGE_OF["cdl_expires"]


def test_errors_and_warnings_are_distinguished() -> None:
    flags = run(cdl_expires=us(days(30)))
    warning = next(f for f in flags if f.rule_id == "cdl.expiring_soon")
    assert warning.severity == "warning"

    flags = run(cdl_expires=us(days(-1)))
    error = next(f for f in flags if f.rule_id == "cdl.expired")
    assert error.severity == "error"


# --------------------------------------------------------------------------
# field.missing / field.blank
# --------------------------------------------------------------------------


def test_field_missing_fires_when_a_required_field_is_not_found() -> None:
    flags = run(cdl_number=MISSING)
    flag = next(f for f in flags if f.rule_id == "field.missing")
    assert flag.field_key == "cdl_number"
    assert "CDL Number" in flag.message


def test_field_missing_does_not_fire_for_an_optional_field() -> None:
    assert "field.missing" not in ids(address=MISSING)


def test_field_blank_fires_when_a_required_field_is_empty() -> None:
    flags = run(cdl_number="")
    blank = [f for f in flags if f.rule_id == "field.blank"]
    assert [f.field_key for f in blank] == ["cdl_number"]


def test_field_blank_does_not_fire_when_the_field_has_a_value() -> None:
    assert "field.blank" not in ids()


def test_a_blank_field_raises_one_flag_not_two() -> None:
    """A blank SSN is one problem. It should read as one problem."""

    assert ids(ssn="") == {"field.blank"}


# --------------------------------------------------------------------------
# SSN
# --------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["12345678", "1234567890", "123-45-678"])
def test_ssn_length_fires(value: str) -> None:
    assert "ssn.length" in ids(ssn=value)


@pytest.mark.parametrize("value", ["123456789", "123-45-6789", "123 45 6789"])
def test_ssn_length_does_not_fire(value: str) -> None:
    assert "ssn.length" not in ids(ssn=value)


def test_ssn_message_never_echoes_the_number() -> None:
    """The driver note gets pasted into a text message. No SSNs in it."""

    for value in ("12345678", "000-45-6789", "123-00-6789"):
        for flag in run(ssn=value):
            if flag.field_key == "ssn":
                digits = "".join(c for c in value if c.isdigit())
                assert digits not in flag.message.replace("-", "").replace(" ", "")


@pytest.mark.parametrize(
    "value",
    ["000-45-6789", "666-45-6789", "900-45-6789", "999-45-6789", "123-00-6789", "123-45-0000"],
)
def test_ssn_invalid_fires(value: str) -> None:
    assert "ssn.invalid" in ids(ssn=value)


@pytest.mark.parametrize("value", ["123-45-6789", "001-01-0001", "899-99-9999"])
def test_ssn_invalid_does_not_fire(value: str) -> None:
    assert "ssn.invalid" not in ids(ssn=value)


# --------------------------------------------------------------------------
# CDL
# --------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["XX", "Ohio", "O"])
def test_cdl_state_invalid_fires(value: str) -> None:
    assert "cdl.state_invalid" in ids(cdl_state=value)


@pytest.mark.parametrize("value", ["OH", "oh", "DC", "AK"])
def test_cdl_state_invalid_does_not_fire(value: str) -> None:
    assert "cdl.state_invalid" not in ids(cdl_state=value)


@pytest.mark.parametrize("value", ["OH 447/19*02", "AB!1234", "12"])
def test_cdl_number_format_fires(value: str) -> None:
    assert "cdl.number_format" in ids(cdl_number=value)


@pytest.mark.parametrize("value", ["OH4471902", "S123-4567-8901", "D0001234"])
def test_cdl_number_format_does_not_fire(value: str) -> None:
    assert "cdl.number_format" not in ids(cdl_number=value)


def test_cdl_issue_unreadable_fires() -> None:
    assert "cdl.issue_unreadable" in ids(cdl_issued="March-ish 2020")


def test_cdl_issue_unreadable_does_not_fire() -> None:
    assert "cdl.issue_unreadable" not in ids(cdl_issued="03/01/2020")


def test_cdl_issue_future_fires() -> None:
    assert "cdl.issue_future" in ids(cdl_issued=us(days(1)))


def test_cdl_issue_future_does_not_fire_for_today() -> None:
    assert "cdl.issue_future" not in ids(cdl_issued=us(days(0)))


def test_cdl_expired_fires_for_yesterday() -> None:
    flags = run(cdl_expires=us(days(-1)))
    flag = next(f for f in flags if f.rule_id == "cdl.expired")
    assert flag.message == f"CDL expired on {us(days(-1))}."


def test_cdl_expired_fires_on_the_expiry_day_itself() -> None:
    """Boundary: "on or before today" includes today."""

    assert "cdl.expired" in ids(cdl_expires=us(days(0)))


def test_cdl_expired_does_not_fire_for_tomorrow() -> None:
    assert "cdl.expired" not in ids(cdl_expires=us(days(1)))


def test_cdl_expiring_soon_fires_within_sixty_days() -> None:
    assert "cdl.expiring_soon" in ids(cdl_expires=us(days(60)))


def test_cdl_expiring_soon_does_not_fire_at_sixty_one_days() -> None:
    assert "cdl.expiring_soon" not in ids(cdl_expires=us(days(61)))


def test_an_expired_cdl_is_not_also_reported_as_expiring_soon() -> None:
    assert "cdl.expiring_soon" not in ids(cdl_expires=us(days(-1)))


def test_cdl_expiry_before_issue_fires() -> None:
    assert "cdl.expiry_before_issue" in ids(
        cdl_issued=us(years(1)), cdl_expires=us(days(30))
    )


def test_cdl_expiry_before_issue_does_not_fire() -> None:
    assert "cdl.expiry_before_issue" not in ids()


# --------------------------------------------------------------------------
# Date of birth
# --------------------------------------------------------------------------


def test_dob_unreadable_fires() -> None:
    assert "dob.unreadable" in ids(dob="not a date")


def test_dob_unreadable_does_not_fire() -> None:
    assert "dob.unreadable" not in ids(dob="1985-06-01")


def test_dob_under_21_fires() -> None:
    flags = run(dob=us(years(-20)))
    flag = next(f for f in flags if f.rule_id == "dob.under_21")
    assert "391.11" in flag.message


def test_dob_under_21_does_not_fire_on_the_twenty_first_birthday() -> None:
    """Boundary: a driver who turns 21 today is 21 today."""

    birthday = dt.date(
        dt.date.today().year - 21, dt.date.today().month, dt.date.today().day
    )
    assert "dob.under_21" not in ids(dob=us(birthday))


def test_dob_under_21_fires_the_day_before_the_twenty_first_birthday() -> None:
    today = dt.date.today()
    birthday = dt.date(today.year - 21, today.month, today.day) + dt.timedelta(days=1)
    assert "dob.under_21" in ids(dob=us(birthday))


def test_dob_implausible_fires_over_ninety() -> None:
    assert "dob.implausible" in ids(dob=us(years(-95)))


def test_dob_implausible_does_not_fire_at_a_normal_age() -> None:
    assert "dob.implausible" not in ids(dob=us(years(-60)))


# --------------------------------------------------------------------------
# Phone and email
# --------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["555-0142", "216555014", "1234567890123"])
def test_phone_length_fires(value: str) -> None:
    assert "phone.length" in ids(phone=value)


@pytest.mark.parametrize("value", ["(216) 555-0142", "2165550142", "1-216-555-0142"])
def test_phone_length_does_not_fire(value: str) -> None:
    assert "phone.length" not in ids(phone=value)


@pytest.mark.parametrize("value", ["jsmith", "jsmith@", "@example.com", "a b@c.com"])
def test_email_format_fires(value: str) -> None:
    assert "email.format" in ids(email=value)


@pytest.mark.parametrize("value", ["jsmith@example.com", "j.smith+dq@mail.co.uk"])
def test_email_format_does_not_fire(value: str) -> None:
    assert "email.format" not in ids(email=value)


# --------------------------------------------------------------------------
# Signature
# --------------------------------------------------------------------------


def test_signature_driver_missing_fires_when_the_block_is_empty() -> None:
    assert "signature.driver_missing" in ids(driver_signature="")


def test_signature_driver_missing_does_not_fire_when_signed() -> None:
    assert "signature.driver_missing" not in ids()


def test_an_empty_signature_block_reports_once() -> None:
    assert ids(driver_signature="") == {"signature.driver_missing"}


def test_signature_date_unreadable_fires() -> None:
    assert "signature.date_unreadable" in ids(signature_date="sometime last week")


def test_signature_date_unreadable_does_not_fire() -> None:
    assert "signature.date_unreadable" not in ids()


def test_signature_date_future_fires() -> None:
    assert "signature.date_future" in ids(signature_date=us(days(1)))


def test_signature_date_future_does_not_fire_for_today() -> None:
    assert "signature.date_future" not in ids(signature_date=us(days(0)))


# --------------------------------------------------------------------------
# Employment history
# --------------------------------------------------------------------------


def blank_employment() -> dict[str, object]:
    out: dict[str, object] = {}
    for n in (1, 2, 3):
        out[f"emp{n}_company"] = ""
        out[f"emp{n}_from"] = ""
        out[f"emp{n}_to"] = ""
    return out


def jobs(**over: object) -> dict[str, object]:
    """A blank employment section with only the given blocks filled in."""

    out = blank_employment()
    out.update(over)
    return out


def only_first_job(**over: object) -> dict[str, object]:
    """One employer covering the last eleven years, plus overrides."""

    out = blank_employment()
    out.update(
        {
            "emp1_company": "Redline Freight Inc",
            "emp1_from": us(years(-11)),
            "emp1_to": "Present",
        }
    )
    out.update(over)
    return out


def test_employment_none_fires_when_no_history_is_readable() -> None:
    assert "employment.none" in ids(**blank_employment())


def test_employment_none_does_not_fire_when_history_exists() -> None:
    assert "employment.none" not in ids()


def test_employment_company_missing_fires() -> None:
    assert "employment.company_missing" in ids(**only_first_job(emp1_company=""))


def test_employment_company_missing_does_not_fire() -> None:
    assert "employment.company_missing" not in ids()


def test_employment_date_unreadable_fires_on_garbage() -> None:
    assert "employment.date_unreadable" in ids(**only_first_job(emp1_from="last spring"))


def test_employment_date_unreadable_fires_on_a_blank_date() -> None:
    assert "employment.date_unreadable" in ids(**only_first_job(emp1_to=""))


def test_employment_date_unreadable_does_not_fire() -> None:
    assert "employment.date_unreadable" not in ids()


def test_employment_reversed_fires() -> None:
    assert "employment.reversed" in ids(
        **only_first_job(emp1_from=us(days(-100)), emp1_to=us(days(-200)))
    )


def test_employment_reversed_does_not_fire() -> None:
    assert "employment.reversed" not in ids()


def test_employment_gap_does_not_fire_at_exactly_thirty_days() -> None:
    """Boundary: the rule is "over 30 days"."""

    flags = ids(
        **jobs(
            emp1_company="Redline Freight Inc",
            emp1_from=us(days(-100)),
            emp1_to="Present",
            emp2_company="Great Lakes Carriers",
            emp2_from=us(years(-11)),
            emp2_to=us(days(-130)),
        )
    )
    assert "employment.gap" not in flags


def test_employment_gap_fires_at_thirty_one_days() -> None:
    flags = ids(
        **jobs(
            emp1_company="Redline Freight Inc",
            emp1_from=us(days(-100)),
            emp1_to="Present",
            emp2_company="Great Lakes Carriers",
            emp2_from=us(years(-11)),
            emp2_to=us(days(-131)),
        )
    )
    assert "employment.gap" in flags


def test_the_gap_message_names_both_employers_and_the_length() -> None:
    message = message_for(
        "employment.gap",
        **jobs(
            emp1_company="Redline Freight Inc",
            emp1_from=us(days(-100)),
            emp1_to="Present",
            emp2_company="Great Lakes Carriers",
            emp2_from=us(years(-11)),
            emp2_to=us(days(-160)),
        ),
    )
    assert "60-day gap" in message
    assert "Great Lakes Carriers" in message
    assert "Redline Freight Inc" in message


def test_overlapping_jobs_are_not_a_gap() -> None:
    flags = ids(
        **jobs(
            emp1_company="Redline Freight Inc",
            emp1_from=us(years(-5)),
            emp1_to="Present",
            emp2_company="Great Lakes Carriers",
            emp2_from=us(years(-11)),
            emp2_to=us(years(-4)),
        )
    )
    assert "employment.gap" not in flags


def test_employment_recent_gap_fires() -> None:
    assert "employment.recent_gap" in ids(**only_first_job(emp1_to=us(days(-45))))


def test_employment_recent_gap_does_not_fire_at_exactly_thirty_days() -> None:
    assert "employment.recent_gap" not in ids(**only_first_job(emp1_to=us(days(-30))))


def test_employment_recent_gap_fires_at_thirty_one_days() -> None:
    assert "employment.recent_gap" in ids(**only_first_job(emp1_to=us(days(-31))))


@pytest.mark.parametrize("ending", ["Present", "current", "PRESENT"])
def test_a_current_job_ends_today(ending: str) -> None:
    assert "employment.recent_gap" not in ids(**only_first_job(emp1_to=ending))


def test_employment_under_3_years_fires() -> None:
    flags = run(**only_first_job(emp1_from=us(years(-2))))
    flag = next(f for f in flags if f.rule_id == "employment.under_3_years")
    assert "391.21" in flag.message


def test_employment_under_3_years_does_not_fire_at_exactly_three_years() -> None:
    assert "employment.under_3_years" not in ids(
        **only_first_job(emp1_from=us(years(-3)))
    )


def test_employment_under_10_years_fires_as_a_warning() -> None:
    flags = run(**only_first_job(emp1_from=us(years(-6))))
    flag = next(f for f in flags if f.rule_id == "employment.under_10_years")
    assert flag.severity == "warning"


def test_employment_under_10_years_does_not_fire_past_ten_years() -> None:
    assert "employment.under_10_years" not in ids()


def test_short_history_reports_the_error_not_both_thresholds() -> None:
    """Under three years is already under ten. One flag, not two."""

    flags = ids(**only_first_job(emp1_from=us(years(-1))))
    assert "employment.under_3_years" in flags
    assert "employment.under_10_years" not in flags


# --------------------------------------------------------------------------
# Date parsing
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("03/01/2025", dt.date(2025, 3, 1)),
        ("03-01-2025", dt.date(2025, 3, 1)),
        ("2025-03-01", dt.date(2025, 3, 1)),
        ("03/01/25", dt.date(2025, 3, 1)),
        ("1 Mar 2025", dt.date(2025, 3, 1)),
        ("March 1, 2025", dt.date(2025, 3, 1)),
        ("  03/01/2025  ", dt.date(2025, 3, 1)),
    ],
)
def test_parse_date_accepts_every_documented_format(text: str, expected: dt.date) -> None:
    assert parse_date(text) == expected


@pytest.mark.parametrize("text", ["", "   ", "13/45/2025", "sometime", "01/2025"])
def test_parse_date_rejects_the_unparseable(text: str) -> None:
    assert parse_date(text) is None


def test_an_unparseable_date_is_an_error_not_a_silent_skip() -> None:
    flags = run(cdl_expires="whenever")
    assert [f.severity for f in flags if f.field_key == "cdl_expires"] == ["error"]


# --------------------------------------------------------------------------
# Required-ness comes from the field map
# --------------------------------------------------------------------------


def test_a_field_map_can_make_a_field_optional() -> None:
    specs = [
        FieldSpec(field_key="email", label="Email", anchors=["Email"], required=False)
    ]
    fields = [ExtractedValue("email", "Email", "", 1, True)]
    assert validate(fields, specs) == []
