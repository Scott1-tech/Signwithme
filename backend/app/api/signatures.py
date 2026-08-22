"""The signature library.

A carrier usually has more than one person who can sign, so signatures are
kept as a named library rather than a single configured file. The reviewer
picks which one to stamp when uploading a contract.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Contract, SignatureAsset
from app.schemas import SignatureAssetOut, SignatureRename
from app.security import hash_bytes

logger = logging.getLogger("contract_desk.signatures")

router = APIRouter(prefix="/signatures", tags=["signatures"])

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
MAX_SIGNATURE_BYTES = 4 * 1024 * 1024


def _get(session: Session, signature_id: str) -> SignatureAsset:
    asset = session.get(SignatureAsset, signature_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Signature not found.")
    return asset


def _path(asset: SignatureAsset):
    return get_settings().signatures_dir / asset.filename


@router.get("", response_model=list[SignatureAssetOut])
def list_signatures(session: Session = Depends(get_db)) -> list[SignatureAssetOut]:
    rows = session.scalars(
        select(SignatureAsset).order_by(
            SignatureAsset.is_default.desc(), SignatureAsset.created_at.desc()
        )
    ).all()
    return [SignatureAssetOut.model_validate(row) for row in rows]


@router.post("", response_model=SignatureAssetOut, status_code=201)
def create_signature(
    file: UploadFile = File(...),
    name: str = Form(...),
    session: Session = Depends(get_db),
) -> SignatureAssetOut:
    label = name.strip()
    if not label:
        raise HTTPException(status_code=400, detail="Give the signature a name.")

    data = file.file.read()
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(data) > MAX_SIGNATURE_BYTES:
        raise HTTPException(status_code=400, detail="The image is larger than 4 MB.")
    if not data.startswith(PNG_MAGIC):
        raise HTTPException(
            status_code=400,
            detail="The signature must be a PNG. A transparent background "
            "stamps most cleanly.",
        )

    settings = get_settings()
    settings.ensure_directories()

    asset = SignatureAsset(
        name=label,
        filename="",
        file_hash=hash_bytes(data),
        # The first one uploaded becomes the default.
        is_default=session.scalar(select(SignatureAsset).limit(1)) is None,
    )
    session.add(asset)
    session.flush()

    asset.filename = f"{asset.id}.png"
    (settings.signatures_dir / asset.filename).write_bytes(data)
    session.flush()

    logger.info("signature saved id=%s bytes=%s", asset.id, len(data))
    return SignatureAssetOut.model_validate(asset)


@router.get("/{signature_id}/image")
def signature_image(
    signature_id: str, session: Session = Depends(get_db)
) -> FileResponse:
    asset = _get(session, signature_id)
    path = _path(asset)
    if not path.exists():
        raise HTTPException(status_code=404, detail="The signature file is missing.")
    return FileResponse(path, media_type="image/png")


@router.patch("/{signature_id}", response_model=SignatureAssetOut)
def rename_signature(
    signature_id: str, body: SignatureRename, session: Session = Depends(get_db)
) -> SignatureAssetOut:
    asset = _get(session, signature_id)
    asset.name = body.name.strip()
    session.flush()
    return SignatureAssetOut.model_validate(asset)


@router.post("/{signature_id}/default", response_model=SignatureAssetOut)
def make_default(
    signature_id: str, session: Session = Depends(get_db)
) -> SignatureAssetOut:
    asset = _get(session, signature_id)
    for other in session.scalars(select(SignatureAsset)).all():
        other.is_default = other.id == asset.id
    session.flush()
    return SignatureAssetOut.model_validate(asset)


@router.delete("/{signature_id}", status_code=204)
def delete_signature(
    signature_id: str, session: Session = Depends(get_db)
) -> Response:
    asset = _get(session, signature_id)

    used_by = session.scalar(
        select(Contract.id).where(Contract.signature_asset_id == asset.id).limit(1)
    )
    if used_by:
        raise HTTPException(
            status_code=409,
            detail="This signature has been stamped on a contract, so it is "
            "kept as part of the record. It cannot be deleted.",
        )

    path = _path(asset)
    if path.exists():
        path.unlink()
    session.delete(asset)
    session.flush()
    return Response(status_code=204)
