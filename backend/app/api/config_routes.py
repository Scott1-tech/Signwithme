"""Configuration routes: field map, carrier details, signature, probe.

This is where day one of the build plan is spent — pointing the field map at
the labels a real contract actually uses, and getting the signature to land
in the right place.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Contract
from app.schemas import (
    CarrierOut,
    FieldMapOut,
    ProbeOut,
    ProbePageOut,
    ProbeWidgetOut,
    TestPlacementRequest,
)
from app.services import config_store, extract, files, stamp

logger = logging.getLogger("contract_desk.config")

router = APIRouter(prefix="/config", tags=["config"])

SIGNATURE_FILENAME = "carrier_signature.png"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


# --------------------------------------------------------------------------
# Field map
# --------------------------------------------------------------------------


@router.get("/fields", response_model=FieldMapOut)
def get_fields() -> FieldMapOut:
    return FieldMapOut.of(config_store.load_field_map())


@router.put("/fields", response_model=FieldMapOut)
def put_fields(body: FieldMapOut) -> FieldMapOut:
    if not body.contract_types:
        raise HTTPException(
            status_code=400, detail="The field map needs at least one contract type."
        )

    for contract_type, specs in body.contract_types.items():
        keys = [spec.field_key for spec in specs]
        duplicates = {key for key in keys if keys.count(key) > 1}
        if duplicates:
            raise HTTPException(
                status_code=400,
                detail=f"Duplicate field keys in {contract_type}: "
                + ", ".join(sorted(duplicates)),
            )

    saved = config_store.save_field_map(
        config_store.FieldMap(contract_types=body.contract_types)
    )
    logger.info("field map saved types=%s", list(saved.contract_types))
    return FieldMapOut.of(saved)


@router.post("/fields/reset", response_model=FieldMapOut)
def reset_fields() -> FieldMapOut:
    """Restore the starting field map, for when an edit goes wrong."""

    return FieldMapOut.of(config_store.save_field_map(config_store.FieldMap.default()))


# --------------------------------------------------------------------------
# Carrier details and signature placement
# --------------------------------------------------------------------------


def _carrier_out(carrier: config_store.CarrierConfig) -> CarrierOut:
    return CarrierOut(
        **carrier.model_dump(),
        signature_uploaded=config_store.signature_path() is not None,
    )


@router.get("/carrier", response_model=CarrierOut)
def get_carrier() -> CarrierOut:
    return _carrier_out(config_store.load_carrier())


@router.put("/carrier", response_model=CarrierOut)
def put_carrier(body: CarrierOut) -> CarrierOut:
    payload = body.model_dump(exclude={"signature_uploaded"})
    # The signature filename is owned by the upload route, not the form.
    payload["signature_file"] = config_store.load_carrier().signature_file
    saved = config_store.save_carrier(config_store.CarrierConfig(**payload))
    logger.info("carrier config saved")
    return _carrier_out(saved)


@router.post("/signature", response_model=CarrierOut)
def upload_signature(file: UploadFile = File(...)) -> CarrierOut:
    data = file.file.read()
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if not data.startswith(PNG_MAGIC):
        raise HTTPException(
            status_code=400,
            detail="The signature must be a PNG. A transparent background "
            "stamps most cleanly.",
        )

    settings = get_settings()
    settings.ensure_directories()
    destination = settings.signatures_dir / SIGNATURE_FILENAME
    destination.write_bytes(data)

    carrier = config_store.load_carrier()
    carrier.signature_file = SIGNATURE_FILENAME
    config_store.save_carrier(carrier)
    logger.info("signature image uploaded bytes=%s", len(data))

    return _carrier_out(carrier)


@router.get("/signature")
def get_signature() -> FileResponse:
    """The configured signature image, for the settings-screen preview."""

    path = config_store.signature_path()
    if path is None:
        raise HTTPException(status_code=404, detail="No signature image configured.")
    return FileResponse(path, media_type="image/png")


# --------------------------------------------------------------------------
# Probe and placement preview
# --------------------------------------------------------------------------


@router.post("/probe", response_model=ProbeOut)
def probe_pdf(file: UploadFile = File(...)) -> ProbeOut:
    """Report what a sample PDF actually contains.

    Widget values are never returned — a real contract carries a Social
    Security number and the wizard only needs the names.
    """

    data = file.file.read()
    if not files.is_pdf(data):
        raise HTTPException(status_code=400, detail="That file is not a PDF.")

    settings = get_settings()
    settings.ensure_directories()
    scratch = settings.uploads_dir / "_probe.pdf"
    scratch.write_bytes(data)
    try:
        result = extract.probe(scratch)
    finally:
        scratch.unlink(missing_ok=True)

    return ProbeOut(
        page_count=result.page_count,
        has_acroform=result.has_acroform,
        widgets=[
            ProbeWidgetOut(page=w.page, name=w.name, type=w.type, has_value=w.has_value)
            for w in result.widgets
        ],
        pages=[ProbePageOut(page=p.page, text=p.text) for p in result.pages],
    )


@router.post("/test-placement")
def test_placement(
    body: TestPlacementRequest, session: Session = Depends(get_db)
) -> Response:
    """Preview a placement against a real contract without saving it."""

    contract = session.get(Contract, body.contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found.")

    path = files.absolute(contract.stored_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="The stored PDF is missing.")

    placements = stamp.resolve_placements(path, body.signature)
    if not placements:
        raise HTTPException(
            status_code=404,
            detail="Nothing matched. The anchor phrase was not found on any "
            "page, and no fallback pages are set.",
        )

    page_no = body.page or placements[0].page
    try:
        png = stamp.preview_page(path, page_no, boxes=True, placements=placements)
    except IndexError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Cache-Control": "no-store",
            # Lets the settings screen say which page it is showing.
            "X-Preview-Page": str(page_no),
            "X-Placement-Count": str(len(placements)),
            "X-Placement-Pages": ",".join(str(p.page) for p in placements),
            "Access-Control-Expose-Headers": (
                "X-Preview-Page, X-Placement-Count, X-Placement-Pages"
            ),
        },
    )
