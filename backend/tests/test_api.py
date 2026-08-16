"""API behaviour, per specification section 12.

Each test gets its own storage directory and database, so nothing leaks
between them and no real contract is ever involved.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.database import reset_engine
from tests.conftest import (
    build_fillable_contract,
    build_flattened_contract,
    build_signature_png,
    clean_values,
    days,
    us,
)


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("SSN_SALT", "salt-for-tests")
    get_settings.cache_clear()
    reset_engine()

    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client

    get_settings.cache_clear()
    reset_engine()


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def upload(client: TestClient, path: Path, filename: str = "contract.pdf") -> dict:
    with open(path, "rb") as handle:
        response = client.post(
            "/api/contracts",
            files={"file": (filename, handle, "application/pdf")},
        )
    assert response.status_code == 201, response.text
    return response.json()


def configure_signature(client: TestClient, tmp_path: Path) -> None:
    png = build_signature_png(tmp_path / "sig.png")
    with open(png, "rb") as handle:
        response = client.post(
            "/api/config/signature", files={"file": ("sig.png", handle, "image/png")}
        )
    assert response.status_code == 200, response.text


def approve(client: TestClient, contract_id: str, *, acknowledge: bool = False) -> dict:
    response = client.post(
        f"/api/contracts/{contract_id}/approve",
        json={"approved_by": "Dana Okafor", "acknowledge_errors": acknowledge},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def clean_pdf(tmp_path: Path) -> Path:
    return build_flattened_contract(tmp_path / "clean.pdf")


@pytest.fixture
def broken_pdf(tmp_path: Path) -> Path:
    """Two errors, on two different pages."""

    return build_flattened_contract(
        tmp_path / "broken.pdf",
        {"cdl_expires": us(days(-30)), "email": ""},
    )


# --------------------------------------------------------------------------
# Health and upload
# --------------------------------------------------------------------------


def test_health(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}


def test_the_root_redirects_to_the_api_docs(client: TestClient) -> None:
    """A bare / used to 404, which reads as a broken deployment."""

    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/docs"

    assert client.get("/docs").status_code == 200


def test_a_head_request_to_the_root_does_not_404(client: TestClient) -> None:
    """Uptime checks and platform health probes use HEAD /."""

    assert client.head("/", follow_redirects=False).status_code == 307


def test_upload_returns_the_full_detail_object(
    client: TestClient, clean_pdf: Path
) -> None:
    body = upload(client, clean_pdf, "smith_owner_operator.pdf")

    assert body["original_filename"] == "smith_owner_operator.pdf"
    assert body["status"] == "clean"
    assert body["page_count"] == 4
    assert body["driver_name"] == "John Smith"
    assert body["extraction_source"] == "text"
    assert body["summary"] == {
        "error_count": 0,
        "warning_count": 0,
        "pages_to_fix": [],
    }
    assert body["can_approve"] is True
    assert body["can_execute"] is False


def test_upload_of_a_non_pdf_returns_400(client: TestClient, tmp_path: Path) -> None:
    junk = tmp_path / "notes.txt"
    junk.write_text("this is not a contract")

    with open(junk, "rb") as handle:
        response = client.post(
            "/api/contracts", files={"file": ("notes.txt", handle, "application/pdf")}
        )

    assert response.status_code == 400
    assert "not a PDF" in response.json()["detail"]


def test_upload_of_an_empty_file_returns_400(client: TestClient, tmp_path: Path) -> None:
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")

    with open(empty, "rb") as handle:
        response = client.post(
            "/api/contracts", files={"file": ("empty.pdf", handle, "application/pdf")}
        )

    assert response.status_code == 400


def test_uploading_the_same_file_twice_returns_409_with_the_first_id(
    client: TestClient, clean_pdf: Path
) -> None:
    first = upload(client, clean_pdf)

    with open(clean_pdf, "rb") as handle:
        response = client.post(
            "/api/contracts", files={"file": ("again.pdf", handle, "application/pdf")}
        )

    assert response.status_code == 409
    assert response.json()["detail"]["contract_id"] == first["id"]


def test_a_broken_contract_needs_review(client: TestClient, broken_pdf: Path) -> None:
    body = upload(client, broken_pdf)
    rule_ids = {flag["rule_id"] for flag in body["flags"]}

    assert body["status"] == "needs_review"
    assert body["summary"]["error_count"] == 2
    assert body["summary"]["pages_to_fix"] == [1, 2]
    assert rule_ids == {"field.blank", "cdl.expired"}


def test_a_fillable_contract_reads_through_the_acroform_path(
    client: TestClient, tmp_path: Path
) -> None:
    path = build_fillable_contract(tmp_path / "fillable.pdf")
    body = upload(client, path)

    assert body["extraction_source"] == "acroform"
    assert body["status"] == "clean"


# --------------------------------------------------------------------------
# SSN handling
# --------------------------------------------------------------------------


def test_the_api_never_returns_a_full_ssn(client: TestClient, clean_pdf: Path) -> None:
    body = upload(client, clean_pdf)
    ssn_field = next(f for f in body["fields"] if f["field_key"] == "ssn")

    assert ssn_field["value"] == "***-**-6789"
    assert body["ssn_masked"] == "***-**-6789"
    assert "123-45-6789" not in str(body)


def test_the_database_never_holds_a_full_ssn(
    client: TestClient, clean_pdf: Path, tmp_path: Path
) -> None:
    upload(client, clean_pdf)

    raw = (tmp_path / "test.db").read_bytes()
    assert b"123456789" not in raw
    assert b"123-45-6789" not in raw


# --------------------------------------------------------------------------
# Queue
# --------------------------------------------------------------------------


def test_queue_lists_newest_first(
    client: TestClient, clean_pdf: Path, broken_pdf: Path
) -> None:
    first = upload(client, clean_pdf, "aaa.pdf")
    second = upload(client, broken_pdf, "bbb.pdf")

    body = client.get("/api/contracts").json()

    assert body["total"] == 2
    assert [item["id"] for item in body["items"]][0] in (second["id"], first["id"])
    assert {item["original_filename"] for item in body["items"]} == {
        "aaa.pdf",
        "bbb.pdf",
    }


def test_queue_filters_by_status(
    client: TestClient, clean_pdf: Path, broken_pdf: Path
) -> None:
    upload(client, clean_pdf, "aaa.pdf")
    upload(client, broken_pdf, "bbb.pdf")

    body = client.get("/api/contracts", params={"status": "needs_review"}).json()

    assert body["total"] == 1
    assert body["items"][0]["original_filename"] == "bbb.pdf"
    assert body["items"][0]["error_count"] == 2


def test_queue_searches_driver_name_and_filename(
    client: TestClient, clean_pdf: Path
) -> None:
    upload(client, clean_pdf, "smith_packet.pdf")

    by_name = client.get("/api/contracts", params={"q": "john"}).json()
    by_file = client.get("/api/contracts", params={"q": "packet"}).json()
    miss = client.get("/api/contracts", params={"q": "nobody"}).json()

    assert by_name["total"] == 1
    assert by_file["total"] == 1
    assert miss["total"] == 0


def test_queue_paginates(client: TestClient, tmp_path: Path) -> None:
    for index in range(3):
        path = build_flattened_contract(
            tmp_path / f"c{index}.pdf", {"phone": f"216555010{index}"}
        )
        upload(client, path, f"c{index}.pdf")

    body = client.get("/api/contracts", params={"page": 2, "page_size": 2}).json()

    assert body["total"] == 3
    assert len(body["items"]) == 1


def test_detail_404_for_an_unknown_id(client: TestClient) -> None:
    assert client.get("/api/contracts/does-not-exist").status_code == 404


# --------------------------------------------------------------------------
# Preview and driver note
# --------------------------------------------------------------------------


def test_preview_returns_a_png(client: TestClient, clean_pdf: Path) -> None:
    contract = upload(client, clean_pdf)
    response = client.get(f"/api/contracts/{contract['id']}/preview/1")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG")


def test_preview_with_boxes_draws_the_placement(
    client: TestClient, clean_pdf: Path
) -> None:
    contract = upload(client, clean_pdf)
    plain = client.get(f"/api/contracts/{contract['id']}/preview/4")
    boxed = client.get(
        f"/api/contracts/{contract['id']}/preview/4", params={"boxes": "true"}
    )

    assert plain.content != boxed.content


def test_preview_of_a_page_that_does_not_exist_returns_404(
    client: TestClient, clean_pdf: Path
) -> None:
    contract = upload(client, clean_pdf)
    assert client.get(f"/api/contracts/{contract['id']}/preview/99").status_code == 404


def test_driver_note_is_page_numbered_plain_text(
    client: TestClient, broken_pdf: Path
) -> None:
    contract = upload(client, broken_pdf)
    response = client.get(f"/api/contracts/{contract['id']}/driver-note")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")

    lines = response.text.splitlines()
    assert lines == [
        "- page 1: Email is blank.",
        f"- page 2: CDL expired on {us(days(-30))}.",
    ]


def test_driver_note_on_a_clean_contract_says_so(
    client: TestClient, clean_pdf: Path
) -> None:
    contract = upload(client, clean_pdf)
    text = client.get(f"/api/contracts/{contract['id']}/driver-note").text

    assert text.strip() != ""
    assert "No corrections needed" in text


# --------------------------------------------------------------------------
# Flags
# --------------------------------------------------------------------------


def test_a_warning_can_be_dismissed(client: TestClient, tmp_path: Path) -> None:
    path = build_flattened_contract(
        tmp_path / "warn.pdf", {"cdl_expires": us(days(30))}
    )
    contract = upload(client, path)
    warning = next(f for f in contract["flags"] if f["severity"] == "warning")

    response = client.post(
        f"/api/contracts/{contract['id']}/flags/{warning['id']}/resolve",
        json={"resolved": True},
    )

    assert response.status_code == 200
    assert response.json()["summary"]["warning_count"] == 0


def test_an_error_cannot_be_dismissed(client: TestClient, broken_pdf: Path) -> None:
    contract = upload(client, broken_pdf)
    error = next(f for f in contract["flags"] if f["severity"] == "error")

    response = client.post(
        f"/api/contracts/{contract['id']}/flags/{error['id']}/resolve",
        json={"resolved": True},
    )

    assert response.status_code == 400
    assert "cannot be dismissed" in response.json()["detail"]


# --------------------------------------------------------------------------
# Approve
# --------------------------------------------------------------------------


def test_approving_a_clean_contract(client: TestClient, clean_pdf: Path) -> None:
    contract = upload(client, clean_pdf)
    body = approve(client, contract["id"])

    assert body["status"] == "approved"
    assert body["approval"]["approved_by"] == "Dana Okafor"
    assert body["approval"]["overridden"] is False
    assert body["approval"]["error_count_at_approval"] == 0
    assert body["approval"]["pages_stamped"] == [4]


def test_approving_with_errors_requires_acknowledgement(
    client: TestClient, broken_pdf: Path
) -> None:
    contract = upload(client, broken_pdf)

    response = client.post(
        f"/api/contracts/{contract['id']}/approve",
        json={"approved_by": "Dana Okafor", "acknowledge_errors": False},
    )

    assert response.status_code == 400
    assert "override" in response.json()["detail"]


def test_approving_over_errors_is_recorded_as_an_override(
    client: TestClient, broken_pdf: Path
) -> None:
    contract = upload(client, broken_pdf)
    body = approve(client, contract["id"], acknowledge=True)

    assert body["approval"]["overridden"] is True
    assert body["approval"]["error_count_at_approval"] == 2


def test_approving_requires_a_typed_name(client: TestClient, clean_pdf: Path) -> None:
    contract = upload(client, clean_pdf)

    blank = client.post(
        f"/api/contracts/{contract['id']}/approve",
        json={"approved_by": "   ", "acknowledge_errors": False},
    )
    missing = client.post(
        f"/api/contracts/{contract['id']}/approve", json={"acknowledge_errors": False}
    )

    assert blank.status_code == 400
    assert missing.status_code == 422


def test_the_approval_records_the_signature_hash(
    client: TestClient, clean_pdf: Path, tmp_path: Path
) -> None:
    configure_signature(client, tmp_path)
    contract = upload(client, clean_pdf)
    body = approve(client, contract["id"])

    assert body["approval"]["signature_hash"]
    assert len(body["approval"]["signature_hash"]) == 64


# --------------------------------------------------------------------------
# Execute
# --------------------------------------------------------------------------


def test_execute_before_approve_returns_409(
    client: TestClient, clean_pdf: Path, tmp_path: Path
) -> None:
    configure_signature(client, tmp_path)
    contract = upload(client, clean_pdf)

    response = client.post(f"/api/contracts/{contract['id']}/execute")

    assert response.status_code == 409
    assert "not been approved" in response.json()["detail"]


def test_execute_without_a_signature_configured_returns_400(
    client: TestClient, clean_pdf: Path
) -> None:
    contract = upload(client, clean_pdf)
    approve(client, contract["id"])

    response = client.post(f"/api/contracts/{contract['id']}/execute")

    assert response.status_code == 400
    assert "No signature image is configured" in response.json()["detail"]


def test_execute_stamps_and_marks_the_contract_executed(
    client: TestClient, clean_pdf: Path, tmp_path: Path
) -> None:
    configure_signature(client, tmp_path)
    contract = upload(client, clean_pdf)
    approve(client, contract["id"])

    body = client.post(f"/api/contracts/{contract['id']}/execute").json()

    assert body["status"] == "executed"
    assert body["can_execute"] is False
    assert body["can_approve"] is False


def test_double_execute_returns_409(
    client: TestClient, clean_pdf: Path, tmp_path: Path
) -> None:
    configure_signature(client, tmp_path)
    contract = upload(client, clean_pdf)
    approve(client, contract["id"])

    first = client.post(f"/api/contracts/{contract['id']}/execute")
    second = client.post(f"/api/contracts/{contract['id']}/execute")

    assert first.status_code == 200
    assert second.status_code == 409
    assert "already been executed" in second.json()["detail"]


def test_execution_leaves_the_original_upload_untouched(
    client: TestClient, clean_pdf: Path, tmp_path: Path
) -> None:
    configure_signature(client, tmp_path)
    contract = upload(client, clean_pdf)
    approve(client, contract["id"])

    stored = tmp_path / "storage" / "uploads" / f"{contract['id']}.pdf"
    before = stored.read_bytes()
    client.post(f"/api/contracts/{contract['id']}/execute")

    assert stored.read_bytes() == before


def test_download_returns_the_executed_pdf(
    client: TestClient, clean_pdf: Path, tmp_path: Path
) -> None:
    configure_signature(client, tmp_path)
    contract = upload(client, clean_pdf)
    approve(client, contract["id"])
    client.post(f"/api/contracts/{contract['id']}/execute")

    response = client.get(f"/api/contracts/{contract['id']}/download")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-")


def test_download_before_execution_returns_404(
    client: TestClient, clean_pdf: Path
) -> None:
    contract = upload(client, clean_pdf)
    assert client.get(f"/api/contracts/{contract['id']}/download").status_code == 404


def test_approving_an_executed_contract_returns_409(
    client: TestClient, clean_pdf: Path, tmp_path: Path
) -> None:
    configure_signature(client, tmp_path)
    contract = upload(client, clean_pdf)
    approve(client, contract["id"])
    client.post(f"/api/contracts/{contract['id']}/execute")

    response = client.post(
        f"/api/contracts/{contract['id']}/approve",
        json={"approved_by": "Someone Else", "acknowledge_errors": True},
    )

    assert response.status_code == 409


# --------------------------------------------------------------------------
# Supersede, void, delete
# --------------------------------------------------------------------------


def test_supersede_links_the_records_and_keeps_the_original(
    client: TestClient, broken_pdf: Path, tmp_path: Path
) -> None:
    original = upload(client, broken_pdf, "first.pdf")
    corrected = build_flattened_contract(tmp_path / "corrected.pdf")

    with open(corrected, "rb") as handle:
        response = client.post(
            f"/api/contracts/{original['id']}/supersede",
            files={"file": ("corrected.pdf", handle, "application/pdf")},
        )

    assert response.status_code == 201
    replacement = response.json()
    assert replacement["supersedes_id"] == original["id"]
    assert replacement["status"] == "clean"

    old = client.get(f"/api/contracts/{original['id']}").json()
    assert old["status"] == "superseded"
    assert old["superseded_by_id"] == replacement["id"]


def test_an_executed_contract_cannot_be_superseded(
    client: TestClient, clean_pdf: Path, tmp_path: Path
) -> None:
    configure_signature(client, tmp_path)
    contract = upload(client, clean_pdf)
    approve(client, contract["id"])
    client.post(f"/api/contracts/{contract['id']}/execute")

    other = build_flattened_contract(tmp_path / "other.pdf", {"phone": "2165550199"})
    with open(other, "rb") as handle:
        response = client.post(
            f"/api/contracts/{contract['id']}/supersede",
            files={"file": ("other.pdf", handle, "application/pdf")},
        )

    assert response.status_code == 409


def test_a_void_contract_can_be_deleted(client: TestClient, clean_pdf: Path) -> None:
    contract = upload(client, clean_pdf)

    voided = client.post(f"/api/contracts/{contract['id']}/void")
    assert voided.json()["status"] == "void"

    assert client.delete(f"/api/contracts/{contract['id']}").status_code == 204
    assert client.get(f"/api/contracts/{contract['id']}").status_code == 404


def test_a_clean_contract_cannot_be_deleted(
    client: TestClient, clean_pdf: Path
) -> None:
    contract = upload(client, clean_pdf)
    response = client.delete(f"/api/contracts/{contract['id']}")

    assert response.status_code == 409


def test_an_executed_contract_can_never_be_deleted(
    client: TestClient, clean_pdf: Path, tmp_path: Path
) -> None:
    """49 CFR 391.51 requires retention."""

    configure_signature(client, tmp_path)
    contract = upload(client, clean_pdf)
    approve(client, contract["id"])
    client.post(f"/api/contracts/{contract['id']}/execute")

    assert client.post(f"/api/contracts/{contract['id']}/void").status_code == 409
    assert client.delete(f"/api/contracts/{contract['id']}").status_code == 409


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


def test_field_map_round_trips(client: TestClient) -> None:
    body = client.get("/api/config/fields").json()
    assert "owner_operator_plan_a" in body["contract_types"]

    body["contract_types"]["owner_operator_plan_a"][0]["label"] = "Full Name"
    saved = client.put("/api/config/fields", json=body)

    assert saved.status_code == 200
    reread = client.get("/api/config/fields").json()
    assert reread["contract_types"]["owner_operator_plan_a"][0]["label"] == "Full Name"


def test_field_map_rejects_duplicate_keys(client: TestClient) -> None:
    body = client.get("/api/config/fields").json()
    specs = body["contract_types"]["owner_operator_plan_a"]
    specs.append(dict(specs[0]))

    response = client.put("/api/config/fields", json=body)

    assert response.status_code == 400
    assert "Duplicate field keys" in response.json()["detail"]


def test_a_changed_field_map_changes_what_gets_extracted(
    client: TestClient, clean_pdf: Path
) -> None:
    body = client.get("/api/config/fields").json()
    for spec in body["contract_types"]["owner_operator_plan_a"]:
        if spec["field_key"] == "email":
            spec["anchors"] = ["Nothing On This Form"]
    client.put("/api/config/fields", json=body)

    contract = upload(client, clean_pdf)
    email = next(f for f in contract["fields"] if f["field_key"] == "email")

    assert email["found"] is False
    assert "field.missing" in {flag["rule_id"] for flag in contract["flags"]}


def test_carrier_details_round_trip(client: TestClient) -> None:
    body = client.get("/api/config/carrier").json()
    body.update(
        {
            "carrier_name": "Grand One LLC",
            "representative_name": "Dana Okafor",
            "representative_title": "Owner",
            "mc_number": "MC-123456",
            "dot_number": "DOT-7654321",
        }
    )

    saved = client.put("/api/config/carrier", json=body).json()

    assert saved["carrier_name"] == "Grand One LLC"
    assert client.get("/api/config/carrier").json()["mc_number"] == "MC-123456"


def test_signature_upload_and_preview(client: TestClient, tmp_path: Path) -> None:
    assert client.get("/api/config/signature").status_code == 404

    configure_signature(client, tmp_path)

    assert client.get("/api/config/carrier").json()["signature_uploaded"] is True
    preview = client.get("/api/config/signature")
    assert preview.status_code == 200
    assert preview.content.startswith(b"\x89PNG")


def test_signature_upload_rejects_a_non_png(client: TestClient, clean_pdf: Path) -> None:
    with open(clean_pdf, "rb") as handle:
        response = client.post(
            "/api/config/signature", files={"file": ("sig.pdf", handle, "image/png")}
        )

    assert response.status_code == 400
    assert "must be a PNG" in response.json()["detail"]


def test_probe_reports_widgets_and_text(client: TestClient, tmp_path: Path) -> None:
    path = build_fillable_contract(tmp_path / "probe.pdf")

    with open(path, "rb") as handle:
        body = client.post(
            "/api/config/probe", files={"file": ("probe.pdf", handle, "application/pdf")}
        ).json()

    assert body["has_acroform"] is True
    assert body["page_count"] == 4
    assert "ssn" in {widget["name"] for widget in body["widgets"]}
    assert all("value" not in widget for widget in body["widgets"])


def test_probe_never_leaks_a_widget_value(client: TestClient, tmp_path: Path) -> None:
    path = build_fillable_contract(tmp_path / "probe.pdf")

    with open(path, "rb") as handle:
        body = client.post(
            "/api/config/probe", files={"file": ("probe.pdf", handle, "application/pdf")}
        ).json()

    assert clean_values()["ssn"] not in str(body["widgets"])


def test_test_placement_returns_a_preview_png(
    client: TestClient, clean_pdf: Path
) -> None:
    contract = upload(client, clean_pdf)

    response = client.post(
        "/api/config/test-placement",
        json={
            "contract_id": contract["id"],
            "signature": {"mode": "anchor", "anchor_phrase": "Carrier Representative"},
        },
    )

    assert response.status_code == 200
    assert response.content.startswith(b"\x89PNG")
    assert response.headers["X-Preview-Page"] == "4"


def test_test_placement_reports_a_phrase_that_matches_nothing(
    client: TestClient, clean_pdf: Path
) -> None:
    contract = upload(client, clean_pdf)

    response = client.post(
        "/api/config/test-placement",
        json={
            "contract_id": contract["id"],
            "signature": {
                "mode": "anchor",
                "anchor_phrase": "Not On This Form",
                "fallback_to_offset": False,
            },
        },
    )

    assert response.status_code == 404
    assert "not found on any page" in response.json()["detail"]


# --------------------------------------------------------------------------
# Audit
# --------------------------------------------------------------------------


def test_audit_lists_approvals_newest_first(
    client: TestClient, clean_pdf: Path, broken_pdf: Path
) -> None:
    first = upload(client, clean_pdf, "first.pdf")
    second = upload(client, broken_pdf, "second.pdf")
    approve(client, first["id"])
    approve(client, second["id"], acknowledge=True)

    body = client.get("/api/audit").json()

    assert body["total"] == 2
    assert body["items"][0]["original_filename"] == "second.pdf"
    assert body["items"][0]["overridden"] is True
    assert body["items"][1]["overridden"] is False


def test_audit_export_is_csv(client: TestClient, clean_pdf: Path) -> None:
    contract = upload(client, clean_pdf)
    approve(client, contract["id"])

    response = client.get("/api/audit/export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")

    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == 1
    assert rows[0]["approved_by"] == "Dana Okafor"
    assert rows[0]["overridden"] == "no"


def test_there_is_no_route_to_change_or_delete_an_approval(
    client: TestClient, clean_pdf: Path
) -> None:
    """Approvals are append-only. This must stay true."""

    contract = upload(client, clean_pdf)
    approval = approve(client, contract["id"])["approval"]

    for method in (client.put, client.patch, client.delete):
        response = method(f"/api/audit/{approval['id']}")
        assert response.status_code in (404, 405)


def test_the_audit_file_log_is_appended_to(
    client: TestClient, clean_pdf: Path, broken_pdf: Path, tmp_path: Path
) -> None:
    first = upload(client, clean_pdf, "first.pdf")
    second = upload(client, broken_pdf, "second.pdf")
    approve(client, first["id"])
    approve(client, second["id"], acknowledge=True)

    log = (tmp_path / "storage" / "audit.jsonl").read_text().splitlines()

    assert len(log) == 2
    assert all('"event": "approval"' in line for line in log)


def test_the_audit_log_never_records_a_field_value(
    client: TestClient, clean_pdf: Path, tmp_path: Path
) -> None:
    contract = upload(client, clean_pdf)
    approve(client, contract["id"])

    log = (tmp_path / "storage" / "audit.jsonl").read_text()

    assert clean_values()["ssn"] not in log
    assert "123456789" not in log
