"""The template, signature library, and template-driven signing routes."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Iterator

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.database import reset_engine
from tests.conftest import (
    build_flattened_contract,
    build_signature_png,
    build_signed_contract,
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


def add_signature(client: TestClient, tmp_path: Path, name: str = "Dana Okafor") -> dict:
    png = build_signature_png(tmp_path / f"{name.replace(' ', '_')}.png")
    with open(png, "rb") as handle:
        response = client.post(
            "/api/signatures",
            files={"file": (png.name, handle, "image/png")},
            data={"name": name},
        )
    assert response.status_code == 201, response.text
    return response.json()


def add_template(client: TestClient, tmp_path: Path, name: str = "Owner operator") -> dict:
    source = build_signed_contract(tmp_path / f"{name.replace(' ', '_')}.pdf")
    with open(source, "rb") as handle:
        response = client.post(
            "/api/templates",
            files={"file": (source.name, handle, "application/pdf")},
            data={"name": name, "description": "Learned from a completed packet"},
        )
    assert response.status_code == 201, response.text
    return response.json()


def upload(client: TestClient, path: Path, **form: str) -> dict:
    with open(path, "rb") as handle:
        response = client.post(
            "/api/contracts",
            files={"file": (path.name, handle, "application/pdf")},
            data=form,
        )
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------
# Signature library
# --------------------------------------------------------------------------


def test_signature_library_starts_empty(client: TestClient) -> None:
    assert client.get("/api/signatures").json() == []


def test_saving_a_signature(client: TestClient, tmp_path: Path) -> None:
    saved = add_signature(client, tmp_path)

    assert saved["name"] == "Dana Okafor"
    assert saved["is_default"] is True  # the first one becomes the default
    assert len(saved["file_hash"]) == 64


def test_several_signatures_are_kept(client: TestClient, tmp_path: Path) -> None:
    add_signature(client, tmp_path, "Dana Okafor")
    second = add_signature(client, tmp_path, "Marcus Bell")

    listed = client.get("/api/signatures").json()

    assert {entry["name"] for entry in listed} == {"Dana Okafor", "Marcus Bell"}
    assert second["is_default"] is False


def test_the_default_signature_can_be_changed(
    client: TestClient, tmp_path: Path
) -> None:
    add_signature(client, tmp_path, "Dana Okafor")
    second = add_signature(client, tmp_path, "Marcus Bell")

    client.post(f"/api/signatures/{second['id']}/default")
    listed = {entry["name"]: entry["is_default"] for entry in client.get("/api/signatures").json()}

    assert listed == {"Marcus Bell": True, "Dana Okafor": False}


def test_the_signature_image_can_be_fetched(client: TestClient, tmp_path: Path) -> None:
    saved = add_signature(client, tmp_path)
    response = client.get(f"/api/signatures/{saved['id']}/image")

    assert response.status_code == 200
    assert response.content.startswith(b"\x89PNG")


def test_a_signature_must_be_a_png(client: TestClient, tmp_path: Path) -> None:
    pdf = build_flattened_contract(tmp_path / "not-an-image.pdf")
    with open(pdf, "rb") as handle:
        response = client.post(
            "/api/signatures",
            files={"file": ("sig.pdf", handle, "image/png")},
            data={"name": "Wrong"},
        )

    assert response.status_code == 400
    assert "must be a PNG" in response.json()["detail"]


def test_a_signature_needs_a_name(client: TestClient, tmp_path: Path) -> None:
    png = build_signature_png(tmp_path / "sig.png")
    with open(png, "rb") as handle:
        response = client.post(
            "/api/signatures",
            files={"file": ("sig.png", handle, "image/png")},
            data={"name": "   "},
        )

    assert response.status_code == 400


def test_an_unused_signature_can_be_deleted(client: TestClient, tmp_path: Path) -> None:
    saved = add_signature(client, tmp_path)
    assert client.delete(f"/api/signatures/{saved['id']}").status_code == 204
    assert client.get("/api/signatures").json() == []


# --------------------------------------------------------------------------
# Templates
# --------------------------------------------------------------------------


def test_creating_a_template_from_a_signed_contract(
    client: TestClient, tmp_path: Path
) -> None:
    template = add_template(client, tmp_path)

    assert template["name"] == "Owner operator"
    assert template["page_count"] == 4
    assert template["signature_count"] == 1
    assert template["date_count"] == 1
    assert template["pages_marked"] == [4]
    assert template["ready"] is True


def test_a_template_records_where_each_mark_sits(
    client: TestClient, tmp_path: Path
) -> None:
    template = add_template(client, tmp_path)
    signature = next(m for m in template["marks"] if m["kind"] == "signature")

    assert signature["page"] == 4
    assert signature["width"] > 0
    assert signature["detected_as"] == "image"
    assert "Carrier Representative" in signature["sample_text"]


def test_a_template_from_an_unsigned_contract_is_not_ready(
    client: TestClient, tmp_path: Path
) -> None:
    """Nothing to copy means the reviewer must place marks by hand."""

    plain = build_flattened_contract(tmp_path / "plain.pdf")
    with open(plain, "rb") as handle:
        response = client.post(
            "/api/templates",
            files={"file": ("plain.pdf", handle, "application/pdf")},
            data={"name": "Empty"},
        )

    body = response.json()
    assert response.status_code == 201
    assert body["marks"] == []
    assert body["ready"] is False


def test_templates_are_listed(client: TestClient, tmp_path: Path) -> None:
    add_template(client, tmp_path, "Plan A")
    add_template(client, tmp_path, "Plan B")

    listed = client.get("/api/templates").json()
    assert {entry["name"] for entry in listed} == {"Plan A", "Plan B"}


def test_a_mark_can_be_switched_off(client: TestClient, tmp_path: Path) -> None:
    template = add_template(client, tmp_path)
    marks = [dict(mark) for mark in template["marks"]]
    for mark in marks:
        if mark["kind"] == "date":
            mark["enabled"] = False

    updated = client.put(
        f"/api/templates/{template['id']}", json={"marks": marks}
    ).json()

    assert updated["signature_count"] == 1
    assert updated["date_count"] == 0


def test_a_mark_can_be_added_by_hand(client: TestClient, tmp_path: Path) -> None:
    template = add_template(client, tmp_path)
    marks = [dict(mark) for mark in template["marks"]]
    marks.append(
        {"kind": "signature", "page": 1, "x": 60, "y": 500, "width": 150, "height": 32}
    )

    updated = client.put(
        f"/api/templates/{template['id']}", json={"marks": marks}
    ).json()

    assert updated["signature_count"] == 2
    assert updated["pages_marked"] == [1, 4]


def test_a_mark_beyond_the_last_page_is_refused(
    client: TestClient, tmp_path: Path
) -> None:
    template = add_template(client, tmp_path)
    response = client.put(
        f"/api/templates/{template['id']}",
        json={
            "marks": [
                {"kind": "signature", "page": 99, "x": 1, "y": 1, "width": 10, "height": 10}
            ]
        },
    )

    assert response.status_code == 400
    assert "beyond this template" in response.json()["detail"]


def test_a_template_can_be_renamed(client: TestClient, tmp_path: Path) -> None:
    template = add_template(client, tmp_path)
    updated = client.put(
        f"/api/templates/{template['id']}", json={"name": "Plan A — 2026"}
    ).json()

    assert updated["name"] == "Plan A — 2026"
    assert updated["signature_count"] == 1  # marks left alone


def test_template_preview_is_a_png(client: TestClient, tmp_path: Path) -> None:
    template = add_template(client, tmp_path)
    response = client.get(f"/api/templates/{template['id']}/preview/4")

    assert response.status_code == 200
    assert response.content.startswith(b"\x89PNG")


def test_template_preview_draws_the_marks(client: TestClient, tmp_path: Path) -> None:
    template = add_template(client, tmp_path)
    plain = client.get(f"/api/templates/{template['id']}/preview/4?marks=false")
    boxed = client.get(f"/api/templates/{template['id']}/preview/4?marks=true")

    assert plain.content != boxed.content


def test_an_unused_template_can_be_deleted(client: TestClient, tmp_path: Path) -> None:
    template = add_template(client, tmp_path)
    assert client.delete(f"/api/templates/{template['id']}").status_code == 204
    assert client.get("/api/templates").json() == []


# --------------------------------------------------------------------------
# Signing a new contract from a template
# --------------------------------------------------------------------------


def test_uploading_with_a_template_signature_and_date(
    client: TestClient, tmp_path: Path
) -> None:
    template = add_template(client, tmp_path)
    signature = add_signature(client, tmp_path)
    fresh = build_flattened_contract(tmp_path / "fresh.pdf", {"phone": "2165550133"})

    contract = upload(
        client,
        fresh,
        template_id=template["id"],
        signature_id=signature["id"],
        sign_date="2026-05-04",
    )

    assert contract["template_name"] == "Owner operator"
    assert contract["signature_name"] == "Dana Okafor"
    assert contract["sign_date"] == "2026-05-04"
    assert contract["signature_ready"] is True
    assert [p["how"] for p in contract["placements"]] == ["template", "template"]


def test_the_whole_template_flow_puts_signature_and_date_on_the_page(
    client: TestClient, tmp_path: Path
) -> None:
    template = add_template(client, tmp_path)
    signature = add_signature(client, tmp_path)
    fresh = build_flattened_contract(tmp_path / "fresh.pdf", {"phone": "2165550144"})

    contract = upload(
        client,
        fresh,
        template_id=template["id"],
        signature_id=signature["id"],
        sign_date="2026-05-04",
    )

    approved = client.post(
        f"/api/contracts/{contract['id']}/approve",
        json={"approved_by": "Dana Okafor", "acknowledge_errors": False},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["approval"]["pages_stamped"] == [4]

    executed = client.post(f"/api/contracts/{contract['id']}/execute")
    assert executed.status_code == 200, executed.text
    assert executed.json()["status"] == "executed"

    downloaded = client.get(f"/api/contracts/{contract['id']}/download")
    output = tmp_path / "downloaded.pdf"
    output.write_bytes(downloaded.content)

    with pymupdf.open(str(output)) as doc:
        assert len(doc[3].get_images()) == 1
        assert "05/04/2026" in doc[3].get_text()


def test_the_chosen_date_is_used_not_todays(
    client: TestClient, tmp_path: Path
) -> None:
    template = add_template(client, tmp_path)
    signature = add_signature(client, tmp_path)
    fresh = build_flattened_contract(tmp_path / "fresh.pdf", {"phone": "2165550155"})

    contract = upload(
        client,
        fresh,
        template_id=template["id"],
        signature_id=signature["id"],
        sign_date="2027-01-09",
    )
    client.post(
        f"/api/contracts/{contract['id']}/approve",
        json={"approved_by": "Dana Okafor", "acknowledge_errors": False},
    )
    client.post(f"/api/contracts/{contract['id']}/execute")

    output = tmp_path / "downloaded.pdf"
    output.write_bytes(client.get(f"/api/contracts/{contract['id']}/download").content)

    with pymupdf.open(str(output)) as doc:
        text = doc[3].get_text()

    assert "01/09/2027" in text
    assert dt.date.today().strftime("%m/%d/%Y") not in text


def test_a_bad_date_is_rejected_with_a_readable_message(
    client: TestClient, tmp_path: Path
) -> None:
    fresh = build_flattened_contract(tmp_path / "fresh.pdf")
    with open(fresh, "rb") as handle:
        response = client.post(
            "/api/contracts",
            files={"file": ("fresh.pdf", handle, "application/pdf")},
            data={"sign_date": "next tuesday"},
        )

    assert response.status_code == 400
    assert "not a date" in response.json()["detail"]


def test_an_unknown_template_is_rejected(client: TestClient, tmp_path: Path) -> None:
    fresh = build_flattened_contract(tmp_path / "fresh.pdf")
    with open(fresh, "rb") as handle:
        response = client.post(
            "/api/contracts",
            files={"file": ("fresh.pdf", handle, "application/pdf")},
            data={"template_id": "does-not-exist"},
        )

    assert response.status_code == 400
    assert "no longer exists" in response.json()["detail"]


def test_a_template_with_nothing_enabled_cannot_be_chosen(
    client: TestClient, tmp_path: Path
) -> None:
    template = add_template(client, tmp_path)
    marks = [dict(mark, enabled=False) for mark in template["marks"]]
    client.put(f"/api/templates/{template['id']}", json={"marks": marks})

    fresh = build_flattened_contract(tmp_path / "fresh.pdf")
    with open(fresh, "rb") as handle:
        response = client.post(
            "/api/contracts",
            files={"file": ("fresh.pdf", handle, "application/pdf")},
            data={"template_id": template["id"]},
        )

    assert response.status_code == 400
    assert "nothing switched on" in response.json()["detail"]


def test_a_template_in_use_cannot_be_deleted(
    client: TestClient, tmp_path: Path
) -> None:
    """It is part of the record of how a contract was signed."""

    template = add_template(client, tmp_path)
    signature = add_signature(client, tmp_path)
    fresh = build_flattened_contract(tmp_path / "fresh.pdf", {"phone": "2165550166"})
    upload(
        client,
        fresh,
        template_id=template["id"],
        signature_id=signature["id"],
        sign_date="2026-05-04",
    )

    response = client.delete(f"/api/templates/{template['id']}")
    assert response.status_code == 409
    assert "kept as part of the record" in response.json()["detail"]


def test_a_signature_in_use_cannot_be_deleted(
    client: TestClient, tmp_path: Path
) -> None:
    template = add_template(client, tmp_path)
    signature = add_signature(client, tmp_path)
    fresh = build_flattened_contract(tmp_path / "fresh.pdf", {"phone": "2165550177"})
    upload(
        client,
        fresh,
        template_id=template["id"],
        signature_id=signature["id"],
        sign_date="2026-05-04",
    )

    response = client.delete(f"/api/signatures/{signature['id']}")
    assert response.status_code == 409


def test_uploading_without_a_template_still_works(
    client: TestClient, tmp_path: Path
) -> None:
    """The review-only path is unchanged; templates are opt-in."""

    fresh = build_flattened_contract(tmp_path / "fresh.pdf")
    contract = upload(client, fresh)

    assert contract["template_id"] is None
    assert contract["sign_date"] is None
    assert contract["status"] == "clean"
