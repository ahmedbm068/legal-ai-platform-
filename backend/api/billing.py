"""Staff-side billing: lawyers create and settle client invoices.

Tenant-scoped via standard staff auth + ``apply_tenant_scope``.
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from backend.core.deps import get_current_user, get_db
from backend.core.permissions import apply_tenant_scope
from backend.models.case import Case
from backend.models.client import Client
from backend.models.invoice import Invoice, InvoiceLineItem
from backend.models.tenant import Tenant
from backend.models.user import User
from backend.services.billing_service import (
    generate_invoice_number,
    mark_paid,
    recalculate_total,
    serialize_invoice,
)

router = APIRouter(prefix="/staff/billing", tags=["Staff Billing"])


# ── Schemas ────────────────────────────────────────────────────────────────


class StaffInvoiceLineItemInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    description: str = Field(..., min_length=1, max_length=500)
    hours: float | None = Field(default=None, ge=0)
    amount: float = Field(..., ge=0)


class StaffCreateInvoiceRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    case_id: int
    description: str = Field(..., min_length=1, max_length=255)
    notes: str | None = Field(default=None, max_length=4000)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    line_items: list[StaffInvoiceLineItemInput] = Field(..., min_length=1)


def _staff_case_or_404(db: Session, current_user: User, case_id: int) -> Case:
    query = db.query(Case).filter(Case.id == case_id, Case.deleted_at.is_(None))
    case = apply_tenant_scope(query, Case.tenant_id, current_user).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found.")
    return case


def _scoped_invoice_or_404(db: Session, current_user: User, invoice_id: int) -> Invoice:
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    # Ensure the invoice's case is in the caller's tenant scope.
    case_query = db.query(Case).filter(Case.id == invoice.case_id)
    case = apply_tenant_scope(case_query, Case.tenant_id, current_user).first()
    if not case:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    return invoice


@router.get("")
def list_all_invoices(
    status_filter: str | None = None,
    limit: int = 25,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List invoices across the caller's tenant scope (all tenants for admins).

    Paginated. Returns enriched rows (tenant + client names) plus summary
    totals for outstanding and collected amounts over the full scope.
    """
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    scoped = apply_tenant_scope(
        db.query(Invoice), Invoice.tenant_id, current_user
    )
    if status_filter:
        scoped = scoped.filter(Invoice.status == status_filter.lower())

    total = scoped.count()

    invoices = (
        scoped.order_by(Invoice.issued_at.desc(), Invoice.id.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    # Resolve tenant + client names in bulk to avoid N+1 queries.
    tenant_ids = {inv.tenant_id for inv in invoices}
    client_ids = {inv.client_id for inv in invoices if inv.client_id is not None}
    tenant_names = {
        t.id: t.name
        for t in db.query(Tenant).filter(Tenant.id.in_(tenant_ids)).all()
    } if tenant_ids else {}
    client_names = {
        c.id: c.name
        for c in db.query(Client).filter(Client.id.in_(client_ids)).all()
    } if client_ids else {}

    # Summary totals over the entire scope (not just this page).
    summary_rows = apply_tenant_scope(
        db.query(Invoice.status, Invoice.amount_total),
        Invoice.tenant_id,
        current_user,
    ).all()
    outstanding = sum(
        float(amount or 0)
        for st, amount in summary_rows
        if (st or "").lower() in ("outstanding", "overdue")
    )
    collected = sum(
        float(amount or 0)
        for st, amount in summary_rows
        if (st or "").lower() == "paid"
    )

    rows = []
    for inv in invoices:
        data = serialize_invoice(inv, include_line_items=False)
        data["tenant_id"] = inv.tenant_id
        data["tenant_name"] = tenant_names.get(inv.tenant_id)
        data["client_id"] = inv.client_id
        data["client_name"] = client_names.get(inv.client_id)
        rows.append(data)

    return {
        "invoices": rows,
        "total": total,
        "limit": limit,
        "offset": offset,
        "total_outstanding": outstanding,
        "total_collected": collected,
    }


@router.get("/{case_id}")
def list_case_invoices(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _staff_case_or_404(db, current_user, case_id)
    invoices = (
        db.query(Invoice)
        .filter(Invoice.case_id == case_id)
        .order_by(Invoice.issued_at.desc(), Invoice.id.desc())
        .all()
    )
    return [serialize_invoice(inv) for inv in invoices]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_invoice(
    payload: StaffCreateInvoiceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    case = _staff_case_or_404(db, current_user, payload.case_id)

    invoice = Invoice(
        tenant_id=case.tenant_id,
        case_id=case.id,
        client_id=case.client_id,
        created_by_user_id=current_user.id,
        invoice_number=generate_invoice_number(db),
        description=payload.description.strip(),
        notes=payload.notes,
        currency=payload.currency.upper(),
        status="outstanding",
    )
    for li in payload.line_items:
        invoice.line_items.append(
            InvoiceLineItem(
                description=li.description.strip(),
                hours=Decimal(str(li.hours)) if li.hours is not None else None,
                amount=Decimal(str(li.amount)),
            )
        )
    recalculate_total(invoice)

    db.add(invoice)
    db.commit()
    db.refresh(invoice)

    return serialize_invoice(invoice)


@router.post("/{invoice_id}/mark-paid")
def mark_invoice_paid(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    invoice = _scoped_invoice_or_404(db, current_user, invoice_id)
    mark_paid(db, invoice, provider="manual", reference=f"staff:{current_user.id}")
    return serialize_invoice(invoice)


@router.post("/{invoice_id}/void")
def void_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    invoice = _scoped_invoice_or_404(db, current_user, invoice_id)
    if (invoice.status or "").lower() == "paid":
        raise HTTPException(status_code=400, detail="Cannot void a paid invoice.")
    invoice.status = "void"
    db.commit()
    db.refresh(invoice)
    return serialize_invoice(invoice)
