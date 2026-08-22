"""Placement templates, learned from contracts that were already signed.

The reviewer uploads one completed contract. The app reports the signatures
and dates it can see on it, and where. The reviewer confirms or switches off
each one, and that becomes the template every later contract of that kind is
stamped from.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Contract, MarkKind, Template, TemplateMark
from app.schemas import (
    TemplateListItem,
    TemplateMarkOut,
    TemplateOut,
    TemplateUpdate,
)
from app.services import files, stamp
from app.services import templates as detect

logger = logging.getLogger("contract_desk.templates")

router = APIRouter(prefix="/templates", tags=["templates"])


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _get(session: Session, template_id: str) -> Template:
    template = session.get(Template, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found.")
    return template


def marks_of(template: Template) -> list[stamp.Mark]:
    """The enabled marks, as the stamper wants them."""

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


def to_out(template: Template) -> TemplateOut:
    return TemplateOut(
        id=template.id,
        name=template.name,
        description=template.description,
        source_filename=template.source_filename,
        page_count=template.page_count,
        page_width=template.page_width,
        page_height=template.page_height,
        created_at=template.created_at,
        updated_at=template.updated_at,
        marks=[TemplateMarkOut.model_validate(m) for m in template.marks],
        signature_count=len(template.signature_marks),
        date_count=len(template.date_marks),
        pages_marked=template.pages_marked,
        ready=bool(template.signature_marks or template.date_marks),
    )


def to_list_item(template: Template) -> TemplateListItem:
    return TemplateListItem(
        id=template.id,
        name=template.name,
        description=template.description,
        source_filename=template.source_filename,
        page_count=template.page_count,
        signature_count=len(template.signature_marks),
        date_count=len(template.date_marks),
        pages_marked=template.pages_marked,
        ready=bool(template.signature_marks or template.date_marks),
        created_at=template.created_at,
    )


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------


@router.get("", response_model=list[TemplateListItem])
def list_templates(session: Session = Depends(get_db)) -> list[TemplateListItem]:
    rows = session.scalars(
        select(Template).order_by(Template.created_at.desc())
    ).all()
    return [to_list_item(row) for row in rows]


@router.post("", response_model=TemplateOut, status_code=201)
def create_template(
    file: UploadFile = File(...),
    name: str = Form(...),
    description: str = Form(""),
    detect_dates: bool = Form(True),
    dates_beside_signatures: bool = Form(True),
    session: Session = Depends(get_db),
) -> TemplateOut:
    """Read a completed contract and record where things were stamped."""

    label = name.strip()
    if not label:
        raise HTTPException(status_code=400, detail="Give the template a name.")

    settings = get_settings()
    data = file.file.read()
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
            detail="That file is not a PDF. Use a completed contract that "
            "already has the signature and date on it.",
        )

    settings.ensure_directories()

    template = Template(
        name=label,
        description=description.strip(),
        source_filename=files.safe_stem(file.filename or "template.pdf"),
        source_path="",
    )
    session.add(template)
    session.flush()

    stored = settings.templates_dir / f"{template.id}.pdf"
    stored.write_bytes(data)
    template.source_path = files.relative(stored)

    result = detect.analyze(
        stored,
        include_dates=detect_dates,
        dates_beside_signatures=dates_beside_signatures,
    )
    template.page_count = result.page_count
    template.page_width = result.page_width
    template.page_height = result.page_height

    for ordinal, found in enumerate(result.marks):
        session.add(
            TemplateMark(
                template_id=template.id,
                kind=found.kind,
                page=found.page,
                x=found.x,
                y=found.y,
                width=found.width,
                height=found.height,
                detected_as=found.detected_as,
                sample_text=found.sample_text,
                enabled=True,
                ordinal=ordinal,
            )
        )

    session.flush()
    session.refresh(template)

    logger.info(
        "template created id=%s pages=%s signatures=%s dates=%s",
        template.id,
        result.page_count,
        len(result.signatures),
        len(result.dates),
    )
    return to_out(template)


@router.get("/{template_id}", response_model=TemplateOut)
def get_template(template_id: str, session: Session = Depends(get_db)) -> TemplateOut:
    return to_out(_get(session, template_id))


@router.put("/{template_id}", response_model=TemplateOut)
def update_template(
    template_id: str, body: TemplateUpdate, session: Session = Depends(get_db)
) -> TemplateOut:
    """Rename a template, or correct what was detected.

    Sending ``marks`` replaces the whole set, so the reviewer can switch off
    a false positive, nudge a rectangle, or add a spot the detector missed.
    """

    template = _get(session, template_id)

    if body.name is not None:
        template.name = body.name.strip()
    if body.description is not None:
        template.description = body.description.strip()

    if body.marks is not None:
        for mark in list(template.marks):
            session.delete(mark)
        session.flush()

        for ordinal, incoming in enumerate(body.marks):
            if incoming.page > template.page_count:
                raise HTTPException(
                    status_code=400,
                    detail=f"Page {incoming.page} is beyond this template's "
                    f"{template.page_count} pages.",
                )
            session.add(
                TemplateMark(
                    template_id=template.id,
                    kind=incoming.kind,
                    page=incoming.page,
                    x=incoming.x,
                    y=incoming.y,
                    width=incoming.width,
                    height=incoming.height,
                    detected_as="manual",
                    sample_text=incoming.sample_text,
                    enabled=incoming.enabled,
                    ordinal=ordinal,
                )
            )

    session.flush()
    session.refresh(template)
    return to_out(template)


@router.get("/{template_id}/preview/{page_no}")
def preview_template(
    template_id: str,
    page_no: int,
    marks: bool = True,
    session: Session = Depends(get_db),
) -> Response:
    """The source contract, with the detected marks drawn on it."""

    template = _get(session, template_id)
    path = files.absolute(template.source_path)
    if not path.exists():
        raise HTTPException(
            status_code=404, detail="The template's source PDF is missing."
        )

    try:
        png = stamp.preview_marks(
            path,
            page_no,
            marks_of(template) if marks else [],
        )
    except IndexError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )


@router.delete("/{template_id}", status_code=204)
def delete_template(template_id: str, session: Session = Depends(get_db)) -> Response:
    template = _get(session, template_id)

    used_by = session.scalar(
        select(Contract.id).where(Contract.template_id == template.id).limit(1)
    )
    if used_by:
        raise HTTPException(
            status_code=409,
            detail="This template has been used to stamp a contract, so it "
            "is kept as part of the record. It cannot be deleted.",
        )

    path = files.absolute(template.source_path)
    if path.exists():
        path.unlink()
    session.delete(template)
    session.flush()
    return Response(status_code=204)
