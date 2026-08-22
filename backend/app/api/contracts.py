"""Contract routes: upload, queue, detail, preview, approve, execute."""

from __future__ import annotations

import datetime as dt
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.api.auth import require_auth
from app.database import get_db
from app.models import (
    Approval,
    Contract,
    ContractStatus,
    ExtractedField,
    SignatureAsset,
    Template,
    User,
)
from app.models import Flag as FlagRow
from app.models import Severity
from app.schemas import (
    ApprovalOut,
    ApproveRequest,
    ContractDetail,
    ContractListItem,
    ContractPage,
    FieldOut,
    FlagOut,
    FlagResolveRequest,
    PlacementOut,
    SummaryOut,
)
from app.security import hash_bytes, hash_file, hash_ssn, mask_ssn, ssn_last4
from app.services import audit as audit_service
from app.services import config_store, extract, files, rules, stamp

logger = logging.getLogger("contract_desk.contracts")

router = APIRouter(prefix="/contracts", tags=["contracts"])


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _get_contract(session: Session, contract_id: str) -> Contract:
    contract = session.get(Contract, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found.")
    return contract


def _placements(contract: Contract) -> list[stamp.Placement]:
    path = files.absolute(contract.stored_path)
    if not path.exists():
        return []
    carrier = config_store.load_carrier()
    try:
        return stamp.resolve_placements(path, carrier.placement_for(contract.contract_type))
    except Exception:  # pragma: no cover - a corrupt PDF should not 500 the page
        logger.warning("placement resolution failed contract=%s", contract.id)
        return []


def _template_marks(contract: Contract) -> list[stamp.Mark]:
    """The marks this contract will be stamped with, if it uses a template."""

    template = contract.template
    if template is None:
        return []
    return [
        stamp.Mark(
            kind=mark.kind,
            page=mark.page,
            x=mark.x,
            y=mark.y,
            width=mark.width,
            height=mark.height,
        )
        for mark in template.marks
        if mark.enabled
    ]


def _signature_file(contract: Contract):
    """The signature image to stamp: the one chosen, else the configured one."""

    asset = contract.signature_asset
    if asset is not None:
        path = get_settings().signatures_dir / asset.filename
        return path if path.exists() else None
    return config_store.signature_path()


def _planned_pages(contract: Contract) -> list[int]:
    """Pages that will receive a signature, however placement is decided."""

    if contract.template is not None:
        return sorted({m.page for m in _template_marks(contract) if m.kind == "signature"})
    return [p.page for p in _placements(contract)]


def _superseded_by(session: Session, contract: Contract) -> str | None:
    return session.scalar(
        select(Contract.id).where(Contract.supersedes_id == contract.id)
    )


def to_detail(session: Session, contract: Contract) -> ContractDetail:
    approval = contract.latest_approval
    signature_ready = _signature_file(contract) is not None
    executed = contract.status == ContractStatus.EXECUTED

    return ContractDetail(
        id=contract.id,
        original_filename=contract.original_filename,
        status=contract.status,
        page_count=contract.page_count,
        driver_name=contract.driver_name,
        extraction_source=contract.extraction_source,
        contract_type=contract.contract_type,
        supersedes_id=contract.supersedes_id,
        superseded_by_id=_superseded_by(session, contract),
        ssn_masked=f"***-**-{contract.ssn_last4}" if contract.ssn_last4 else None,
        created_at=contract.created_at,
        updated_at=contract.updated_at,
        summary=SummaryOut(
            error_count=contract.error_count,
            warning_count=contract.warning_count,
            pages_to_fix=contract.pages_to_fix,
        ),
        fields=[FieldOut.model_validate(f) for f in contract.fields],
        flags=[FlagOut.model_validate(f) for f in contract.flags],
        template_id=contract.template_id,
        template_name=contract.template.name if contract.template else None,
        signature_asset_id=contract.signature_asset_id,
        signature_name=(
            contract.signature_asset.name if contract.signature_asset else None
        ),
        sign_date=contract.sign_date,
        placements=(
            [
                PlacementOut(
                    page=m.page,
                    x=m.x,
                    y=m.y,
                    width=m.width,
                    height=m.height,
                    how="template",
                )
                for m in _template_marks(contract)
            ]
            if contract.template is not None
            else [
                PlacementOut(
                    page=p.page, x=p.x, y=p.y, width=p.width, height=p.height, how=p.how
                )
                for p in _placements(contract)
            ]
        ),
        can_approve=contract.status
        not in (
            ContractStatus.EXECUTED,
            ContractStatus.VOID,
            ContractStatus.SUPERSEDED,
        ),
        can_execute=bool(approval) and not executed and signature_ready,
        signature_ready=signature_ready,
        approval=ApprovalOut.model_validate(approval) if approval else None,
    )


def _read_upload(upload: UploadFile) -> bytes:
    settings = get_settings()
    data = upload.file.read()
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"File is larger than the {settings.max_upload_mb} MB limit.",
        )
    if not files.is_pdf(data):
        raise HTTPException(
            status_code=400,
            detail="That file is not a PDF. Download the completed contract "
            "from DocuSign and upload the PDF.",
        )
    return data


def _require_template(session: Session, template_id: str | None) -> Template | None:
    if not template_id:
        return None
    template = session.get(Template, template_id)
    if template is None:
        raise HTTPException(status_code=400, detail="That template no longer exists.")
    if not [m for m in template.marks if m.enabled]:
        raise HTTPException(
            status_code=400,
            detail=f"Template “{template.name}” has nothing switched on to "
            "stamp. Open it and enable at least one signature or date.",
        )
    return template


def _require_signature(
    session: Session, signature_id: str | None
) -> SignatureAsset | None:
    if not signature_id:
        return None
    asset = session.get(SignatureAsset, signature_id)
    if asset is None:
        raise HTTPException(status_code=400, detail="That signature no longer exists.")
    return asset


def _parse_sign_date(value: str | None) -> dt.date | None:
    """Accept the ISO date an HTML date input sends."""

    if not value or not value.strip():
        return None
    try:
        return dt.date.fromisoformat(value.strip())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"“{value}” is not a date the app can read. Use the date "
            "picker, or write it as YYYY-MM-DD.",
        ) from None


def process_upload(
    session: Session,
    *,
    data: bytes,
    filename: str,
    contract_type: str,
    supersedes: Contract | None = None,
    template_id: str | None = None,
    signature_asset_id: str | None = None,
    sign_date: dt.date | None = None,
) -> Contract:
    """Store the file, extract, validate, and persist. Synchronous by design.

    Runs on upload so the reviewer gets an answer on the same request, which
    is what makes the ten-second target in the frontend brief reachable.
    """

    settings = get_settings()
    settings.ensure_directories()

    contract = Contract(
        original_filename=files.safe_stem(filename),
        stored_path="",
        file_hash="",
        contract_type=contract_type,
        status=ContractStatus.UPLOADED,
        supersedes_id=supersedes.id if supersedes else None,
        template_id=template_id,
        signature_asset_id=signature_asset_id,
        sign_date=sign_date,
    )
    session.add(contract)
    session.flush()  # assigns the id we name the file after

    stored = files.write_upload(contract.id, data)
    contract.stored_path = files.relative(stored)
    contract.file_hash = hash_file(stored)

    specs = config_store.load_field_map().for_type(contract_type)
    result = extract.extract(stored, specs)

    contract.page_count = result.page_count
    contract.extraction_source = result.source
    contract.status = ContractStatus.EXTRACTED

    driver_name = (result.value("driver_name") or "").strip()
    contract.driver_name = driver_name or None

    raw_ssn = result.value("ssn")
    contract.ssn_last4 = ssn_last4(raw_ssn)
    contract.ssn_hash = hash_ssn(raw_ssn)

    # Validate against the real values, then persist a masked copy. The full
    # Social Security number never reaches the database.
    flags = rules.validate(result.fields, specs)

    for ordinal, extracted in enumerate(result.fields):
        value = extracted.value
        if extracted.field_key == "ssn" and value:
            value = mask_ssn(value)
        session.add(
            ExtractedField(
                contract_id=contract.id,
                field_key=extracted.field_key,
                label=extracted.label,
                value=value,
                page=extracted.page,
                found=extracted.found,
                ordinal=ordinal,
            )
        )

    for flag in flags:
        session.add(
            FlagRow(
                contract_id=contract.id,
                field_key=flag.field_key,
                page=flag.page,
                severity=flag.severity,
                rule_id=flag.rule_id,
                message=flag.message,
                resolved=False,
            )
        )

    has_errors = any(flag.severity == Severity.ERROR for flag in flags)
    contract.status = (
        ContractStatus.NEEDS_REVIEW if has_errors else ContractStatus.CLEAN
    )

    session.flush()
    session.refresh(contract)

    logger.info(
        "contract processed contract=%s source=%s pages=%s errors=%s warnings=%s",
        contract.id,
        result.source,
        result.page_count,
        sum(1 for f in flags if f.severity == Severity.ERROR),
        sum(1 for f in flags if f.severity == Severity.WARNING),
    )
    return contract


# --------------------------------------------------------------------------
# Upload and queue
# --------------------------------------------------------------------------


@router.post("", response_model=ContractDetail, status_code=201)
def upload_contract(
    file: UploadFile = File(...),
    contract_type: str = Form(config_store.DEFAULT_CONTRACT_TYPE),
    template_id: str | None = Form(None),
    signature_id: str | None = Form(None),
    sign_date: str | None = Form(None),
    session: Session = Depends(get_db),
) -> ContractDetail:
    """Upload a contract, choosing how it will be signed.

    The reviewer picks a template — a contract already signed correctly,
    whose signature and date positions get copied — plus which signature to
    stamp and which date to write. All three are optional here so an upload
    can still be reviewed before those decisions are made.
    """

    data = _read_upload(file)
    digest = hash_bytes(data)

    template = _require_template(session, template_id)
    signature = _require_signature(session, signature_id)
    chosen_date = _parse_sign_date(sign_date)

    existing = session.scalar(
        select(Contract).where(Contract.file_hash == digest).limit(1)
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "This exact file has already been uploaded.",
                "contract_id": existing.id,
                "original_filename": existing.original_filename,
                "status": existing.status,
            },
        )

    contract = process_upload(
        session,
        data=data,
        filename=file.filename or "contract.pdf",
        contract_type=contract_type,
        template_id=template.id if template else None,
        signature_asset_id=signature.id if signature else None,
        sign_date=chosen_date,
    )
    return to_detail(session, contract)


@router.get("", response_model=ContractPage)
def list_contracts(
    status: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 25,
    session: Session = Depends(get_db),
) -> ContractPage:
    page = max(1, page)
    page_size = min(max(1, page_size), 200)

    query = select(Contract)
    if status:
        wanted = [s.strip() for s in status.split(",") if s.strip()]
        query = query.where(Contract.status.in_(wanted))
    if q:
        needle = f"%{q.strip()}%"
        query = query.where(
            or_(
                Contract.driver_name.ilike(needle),
                Contract.original_filename.ilike(needle),
            )
        )

    total = session.scalar(
        select(func.count()).select_from(query.subquery())
    ) or 0

    rows = session.scalars(
        query.order_by(Contract.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return ContractPage(
        items=[
            ContractListItem(
                id=c.id,
                original_filename=c.original_filename,
                driver_name=c.driver_name,
                status=c.status,
                page_count=c.page_count,
                error_count=c.error_count,
                warning_count=c.warning_count,
                template_name=c.template.name if c.template else None,
                signature_name=(
                    c.signature_asset.name if c.signature_asset else None
                ),
                sign_date=c.sign_date,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{contract_id}", response_model=ContractDetail)
def get_contract(
    contract_id: str, session: Session = Depends(get_db)
) -> ContractDetail:
    return to_detail(session, _get_contract(session, contract_id))


# --------------------------------------------------------------------------
# Preview and driver note
# --------------------------------------------------------------------------


@router.get("/{contract_id}/preview/{page_no}")
def preview(
    contract_id: str,
    page_no: int,
    boxes: bool = False,
    executed: bool = False,
    session: Session = Depends(get_db),
) -> Response:
    contract = _get_contract(session, contract_id)

    source = contract.stored_path
    if executed and contract.executed_path:
        source = contract.executed_path
    path = files.absolute(source)
    if not path.exists():
        raise HTTPException(status_code=404, detail="The stored PDF is missing.")

    try:
        png = stamp.preview_page(
            path, page_no, boxes=boxes, placements=_placements(contract) if boxes else None
        )
    except IndexError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=60"},
    )


def build_driver_note(contract: Contract) -> str:
    """Plain text the reviewer pastes into a message to the driver.

    One line per error, page-numbered. No jargon, no rule ids: the driver
    has to be able to act on it.
    """

    errors = [
        flag
        for flag in contract.flags
        if flag.severity == Severity.ERROR and not flag.resolved
    ]
    if not errors:
        return "No corrections needed. Everything on the contract checks out."

    errors.sort(key=lambda f: (f.page if f.page is not None else 10**6, f.field_key))
    lines = []
    for flag in errors:
        if flag.page is not None:
            lines.append(f"- page {flag.page}: {flag.message}")
        else:
            lines.append(f"- {flag.message}")
    return "\n".join(lines)


@router.get("/{contract_id}/driver-note", response_class=PlainTextResponse)
def driver_note(contract_id: str, session: Session = Depends(get_db)) -> str:
    return build_driver_note(_get_contract(session, contract_id))


# --------------------------------------------------------------------------
# Flags
# --------------------------------------------------------------------------


@router.post("/{contract_id}/flags/{flag_id}/resolve", response_model=ContractDetail)
def resolve_flag(
    contract_id: str,
    flag_id: str,
    body: FlagResolveRequest,
    session: Session = Depends(get_db),
) -> ContractDetail:
    """Dismiss a warning.

    Errors cannot be dismissed. A reviewer who disagrees with an error
    approves over it, which is recorded as an override — that distinction is
    the audit trail, so it must not be erasable by clearing the flag.
    """

    contract = _get_contract(session, contract_id)
    flag = session.get(FlagRow, flag_id)
    if flag is None or flag.contract_id != contract.id:
        raise HTTPException(status_code=404, detail="Flag not found.")
    if flag.severity == Severity.ERROR:
        raise HTTPException(
            status_code=400,
            detail="Errors cannot be dismissed. Approve with the override "
            "checkbox if you have context the rules do not.",
        )

    flag.resolved = body.resolved
    session.flush()
    session.refresh(contract)
    return to_detail(session, contract)


# --------------------------------------------------------------------------
# Approve and execute
# --------------------------------------------------------------------------


@router.post("/{contract_id}/approve", response_model=ContractDetail)
def approve(
    contract_id: str,
    body: ApproveRequest,
    request: Request,
    session: Session = Depends(get_db),
    signed_in: User | None = Depends(require_auth),
) -> ContractDetail:
    """Record the human authorisation behind the signature stamp.

    This step is the legal basis for auto-stamping under E-SIGN. It is not
    a formality and must not be defaulted or skipped.
    """

    contract = _get_contract(session, contract_id)

    if contract.status == ContractStatus.EXECUTED:
        raise HTTPException(
            status_code=409, detail="This contract has already been executed."
        )
    if contract.status in (ContractStatus.VOID, ContractStatus.SUPERSEDED):
        raise HTTPException(
            status_code=409,
            detail=f"A {contract.status} contract cannot be approved.",
        )

    approved_by = body.approved_by.strip()
    if not approved_by:
        raise HTTPException(
            status_code=400, detail="Type the name of the approving representative."
        )

    error_count = contract.error_count
    if error_count and not body.acknowledge_errors:
        raise HTTPException(
            status_code=400,
            detail=f"This contract has {error_count} unresolved "
            f"{'error' if error_count == 1 else 'errors'}. Approving anyway "
            "is allowed but will be recorded as an override — confirm to "
            "continue.",
        )

    signature = _signature_file(contract)

    approval = audit_service.record_approval(
        session,
        contract,
        approved_by=approved_by,
        error_count=error_count,
        overridden=bool(error_count),
        # Resolved now so the record states exactly what was authorised.
        pages_stamped=_planned_pages(contract),
        signature_hash=hash_file(signature) if signature else None,
        ip_address=request.client.host if request.client else None,
        # The account, recorded beside the typed name rather than instead
        # of it. The typed name is what the reviewer attested to.
        signed_in_as=signed_in.username if signed_in else None,
    )

    contract.status = ContractStatus.APPROVED
    contract.updated_at = dt.datetime.now(dt.timezone.utc)
    session.flush()
    session.refresh(contract)

    logger.info(
        "contract approved contract=%s approval=%s overridden=%s",
        contract.id,
        approval.id,
        approval.overridden,
    )
    return to_detail(session, contract)


@router.post("/{contract_id}/execute", response_model=ContractDetail)
def execute(contract_id: str, session: Session = Depends(get_db)) -> ContractDetail:
    contract = _get_contract(session, contract_id)

    if contract.status == ContractStatus.EXECUTED:
        raise HTTPException(
            status_code=409,
            detail="This contract has already been executed. Executed "
            "contracts are never re-stamped; upload a correction instead.",
        )

    approval = contract.latest_approval
    if approval is None:
        raise HTTPException(
            status_code=409,
            detail="This contract has not been approved. A reviewer must "
            "authorise the signature before it can be stamped.",
        )

    signature = _signature_file(contract)
    if signature is None:
        raise HTTPException(
            status_code=400,
            detail="No signature image is chosen. Pick one from the signature "
            "library, or upload one on the settings screen.",
        )

    source = files.absolute(contract.stored_path)
    if not source.exists():
        raise HTTPException(status_code=404, detail="The stored PDF is missing.")

    carrier = config_store.load_carrier()
    destination = files.executed_path(contract.id, contract.original_filename)
    template = contract.template

    if template is not None:
        # Copy the placement from the completed contract this was matched to.
        marks = _template_marks(contract)
        if not marks:
            raise HTTPException(
                status_code=400,
                detail=f"Template “{template.name}” has nothing switched on "
                "to stamp.",
            )

        planned = sorted({m.page for m in marks if m.kind == "signature"})
        authorised_pages = sorted(approval.pages_stamped or [])
        if authorised_pages and authorised_pages != planned:
            raise HTTPException(
                status_code=409,
                detail="The template has changed since this contract was "
                "approved. Approve again so the record matches what gets "
                "stamped.",
            )

        result = stamp.apply_marks(
            source,
            destination,
            signature_png=signature,
            marks=marks,
            sign_date=contract.sign_date or approval.approved_at.date(),
            source_page_size=(template.page_width, template.page_height),
            carrier_fills=carrier.acroform_fills,
        )
    else:
        placements = _placements(contract)
        if not placements:
            raise HTTPException(
                status_code=400,
                detail="Could not work out where to place the signature. "
                "Choose a template, or set the anchor phrase on the settings "
                "screen.",
            )

        authorised_pages = sorted(approval.pages_stamped or [])
        if authorised_pages and authorised_pages != sorted(p.page for p in placements):
            raise HTTPException(
                status_code=409,
                detail="The signature placement has changed since this "
                "contract was approved. Approve again so the record matches "
                "what gets stamped.",
            )

        result = stamp.apply(
            source,
            destination,
            signature_png=signature,
            placements=placements,
            config=carrier.placement_for(contract.contract_type),
            signed_on=contract.sign_date or approval.approved_at.date(),
            carrier_fills=carrier.acroform_fills,
        )

    contract.executed_path = files.relative(result.output_path)
    contract.status = ContractStatus.EXECUTED
    contract.updated_at = dt.datetime.now(dt.timezone.utc)
    session.flush()

    audit_service.record_execution(
        contract,
        pages_stamped=result.pages_stamped,
        executed_path=contract.executed_path,
        signature_hash=approval.signature_hash,
    )

    session.refresh(contract)
    return to_detail(session, contract)


@router.get("/{contract_id}/download")
def download(contract_id: str, session: Session = Depends(get_db)) -> FileResponse:
    contract = _get_contract(session, contract_id)
    if not contract.executed_path:
        raise HTTPException(
            status_code=404,
            detail="This contract has not been executed yet, so there is no "
            "signed file to download.",
        )
    path = files.absolute(contract.executed_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="The executed PDF is missing.")

    return FileResponse(
        path,
        media_type="application/pdf",
        filename=path.name,
    )


# --------------------------------------------------------------------------
# Supersede and delete
# --------------------------------------------------------------------------


@router.post("/{contract_id}/supersede", response_model=ContractDetail, status_code=201)
def supersede(
    contract_id: str,
    file: UploadFile = File(...),
    session: Session = Depends(get_db),
) -> ContractDetail:
    """Replace a contract with a corrected upload.

    The old record is kept, not deleted: 49 CFR 391.51 requires the driver
    qualification file to be retained.
    """

    original = _get_contract(session, contract_id)
    if original.status == ContractStatus.EXECUTED:
        raise HTTPException(
            status_code=409,
            detail="An executed contract cannot be superseded. Upload the "
            "correction as a new contract.",
        )

    data = _read_upload(file)
    replacement = process_upload(
        session,
        data=data,
        filename=file.filename or original.original_filename,
        contract_type=original.contract_type,
        supersedes=original,
    )

    original.status = ContractStatus.SUPERSEDED
    original.updated_at = dt.datetime.now(dt.timezone.utc)
    session.flush()
    session.refresh(replacement)

    return to_detail(session, replacement)


@router.post("/{contract_id}/void", response_model=ContractDetail)
def void_contract(
    contract_id: str, session: Session = Depends(get_db)
) -> ContractDetail:
    """Abandon a contract.

    The status model has ``void`` "set by: Human", but section 6 lists no
    route that sets it — which also left DELETE unreachable, since a
    processed contract is ``clean`` or ``needs_review`` and never sits at
    ``uploaded``. This route closes that gap.
    """

    contract = _get_contract(session, contract_id)
    if contract.status == ContractStatus.EXECUTED:
        raise HTTPException(
            status_code=409,
            detail="An executed contract cannot be voided. It is retained "
            "under 49 CFR 391.51.",
        )

    contract.status = ContractStatus.VOID
    contract.updated_at = dt.datetime.now(dt.timezone.utc)
    session.flush()
    session.refresh(contract)
    return to_detail(session, contract)


@router.delete("/{contract_id}", status_code=204)
def delete_contract(contract_id: str, session: Session = Depends(get_db)) -> Response:
    contract = _get_contract(session, contract_id)
    if contract.status not in ContractStatus.DELETABLE:
        raise HTTPException(
            status_code=409,
            detail=f"A {contract.status} contract cannot be deleted. Only "
            "uploaded or void contracts may be removed; executed files are "
            "retained under 49 CFR 391.51.",
        )

    path = files.absolute(contract.stored_path)
    if path.exists():
        path.unlink()

    session.delete(contract)
    session.flush()
    return Response(status_code=204)
