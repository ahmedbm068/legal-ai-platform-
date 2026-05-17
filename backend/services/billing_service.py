"""Billing helpers: invoice numbering, serialization, totals, and the
payment seam.

Payment is processor-agnostic. ``initiate_payment`` is the single place a
real provider (Stripe PaymentIntent, etc.) would be wired. Until one is
configured it returns a structured "not configured" result and does NOT
mark the invoice paid — staff can still settle an invoice out-of-band via
``mark_paid`` (e.g. recorded a bank transfer).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from backend.models.invoice import Invoice, InvoiceLineItem

OUTSTANDING_STATUSES = {"outstanding", "overdue"}
PAID_STATUSES = {"paid"}


def generate_invoice_number(db: Session) -> str:
    """INV-YYYY-NNNNNN, unique. Falls back to a uuid suffix on collision."""
    year = datetime.now(timezone.utc).year
    count = (
        db.query(Invoice)
        .filter(Invoice.invoice_number.like(f"INV-{year}-%"))
        .count()
    )
    candidate = f"INV-{year}-{count + 1:06d}"
    exists = db.query(Invoice.id).filter(Invoice.invoice_number == candidate).first()
    if exists:
        return f"INV-{year}-{uuid.uuid4().hex[:8].upper()}"
    return candidate


def recalculate_total(invoice: Invoice) -> Decimal:
    total = sum((li.amount or Decimal("0")) for li in invoice.line_items)
    invoice.amount_total = total
    return total


def _money(value) -> float:
    if value is None:
        return 0.0
    return float(value)


def serialize_line_item(item: InvoiceLineItem) -> dict:
    return {
        "id": item.id,
        "description": item.description,
        "hours": _money(item.hours) if item.hours is not None else None,
        "amount": _money(item.amount),
    }


def serialize_invoice(invoice: Invoice, *, include_line_items: bool = True) -> dict:
    data = {
        "id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "case_id": invoice.case_id,
        "description": invoice.description,
        "notes": invoice.notes,
        "currency": invoice.currency,
        "amount_total": _money(invoice.amount_total),
        "status": invoice.status,
        "issued_at": invoice.issued_at,
        "due_at": invoice.due_at,
        "paid_at": invoice.paid_at,
        "payment_status": invoice.payment_status,
    }
    if include_line_items:
        data["line_items"] = [serialize_line_item(li) for li in invoice.line_items]
    return data


def outstanding_total(invoices: list[Invoice]) -> float:
    return round(
        sum(
            _money(inv.amount_total)
            for inv in invoices
            if (inv.status or "").lower() in OUTSTANDING_STATUSES
        ),
        2,
    )


def mark_paid(
    db: Session,
    invoice: Invoice,
    *,
    provider: str | None = None,
    reference: str | None = None,
) -> Invoice:
    """Settle an invoice. Idempotent if already paid."""
    if (invoice.status or "").lower() in PAID_STATUSES:
        return invoice
    invoice.status = "paid"
    invoice.paid_at = datetime.now(timezone.utc)
    invoice.payment_provider = provider or invoice.payment_provider or "manual"
    invoice.payment_reference = reference or invoice.payment_reference
    invoice.payment_status = "succeeded"
    db.commit()
    db.refresh(invoice)
    return invoice


class PaymentResult:
    """Outcome of a payment attempt through the processor seam."""

    def __init__(self, *, status: str, message: str, invoice: Invoice):
        self.status = status  # "succeeded" | "not_configured" | "already_paid"
        self.message = message
        self.invoice = invoice


def _payment_provider_configured() -> bool:
    """True only when a real processor is wired. No keys yet -> False.

    When Stripe (or another) is added, gate this on its settings and
    implement the PaymentIntent flow inside ``initiate_payment``.
    """
    return False


def initiate_payment(db: Session, invoice: Invoice) -> PaymentResult:
    """Single entry point for client-initiated payment.

    - already paid           -> no-op, "already_paid"
    - no processor configured -> records an attempt, "not_configured"
                                  (does not mark paid)
    - processor configured    -> (future) create PaymentIntent, etc.
    """
    if (invoice.status or "").lower() in PAID_STATUSES:
        return PaymentResult(
            status="already_paid",
            message="This invoice has already been paid.",
            invoice=invoice,
        )

    if not _payment_provider_configured():
        # Record the intent so staff can see the client tried to pay.
        invoice.payment_status = "pending_provider"
        db.commit()
        db.refresh(invoice)
        return PaymentResult(
            status="not_configured",
            message=(
                "Online payment is not yet enabled for this firm. Your "
                "request has been logged — the firm will follow up with "
                "payment instructions, or you can settle directly with "
                "your legal team."
            ),
            invoice=invoice,
        )

    # Future: create + confirm a real PaymentIntent here, then mark_paid
    # on webhook/confirmation. Unreachable until configured.
    raise NotImplementedError("Payment provider flow not implemented yet.")
