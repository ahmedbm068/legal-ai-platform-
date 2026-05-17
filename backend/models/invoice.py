from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from backend.database.database import Base


class Invoice(Base):
    """A client invoice for legal work on a case.

    Status lifecycle: ``draft`` -> ``outstanding`` -> ``paid``
    (``void`` is terminal). Amounts are stored in minor units of the
    invoice currency would be ideal, but the rest of the app uses plain
    decimals, so we keep ``Numeric(12, 2)`` for consistency and clarity.

    The ``payment_*`` columns are intentionally generic so a real
    processor (Stripe PaymentIntent, etc.) can be wired later without a
    schema change: store its id/status/reference here.
    """

    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)

    tenant_id = Column(Integer, nullable=False, index=True)
    case_id = Column(
        Integer,
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_id = Column(
        Integer,
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    invoice_number = Column(String, nullable=False, unique=True, index=True)
    description = Column(String, nullable=False)
    notes = Column(Text, nullable=True)

    currency = Column(String(3), nullable=False, default="USD")
    amount_total = Column(Numeric(12, 2), nullable=False, default=0)

    # draft | outstanding | paid | void
    status = Column(String(16), nullable=False, default="outstanding", index=True)

    issued_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    due_at = Column(DateTime(timezone=True), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)

    # Generic payment-processor seam (Stripe-ready, processor-agnostic).
    payment_provider = Column(String, nullable=True)
    payment_reference = Column(String, nullable=True)
    payment_status = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    case = relationship("Case")
    client = relationship("Client")
    line_items = relationship(
        "InvoiceLineItem",
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="InvoiceLineItem.id",
    )


class InvoiceLineItem(Base):
    """A single billable line on an invoice (work description, hours, amount)."""

    __tablename__ = "invoice_line_items"

    id = Column(Integer, primary_key=True, index=True)

    invoice_id = Column(
        Integer,
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    description = Column(String, nullable=False)
    hours = Column(Numeric(8, 2), nullable=True)
    amount = Column(Numeric(12, 2), nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    invoice = relationship("Invoice", back_populates="line_items")
