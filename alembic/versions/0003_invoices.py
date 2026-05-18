"""invoices + invoice_line_items tables (client billing)

Revision ID: 0003_invoices
Revises: 0002_case_messages
Create Date: 2026-05-17 00:00:00.000000

Idempotent: most environments bootstrap via ``Base.metadata.create_all``
(schema_sync path), so tables may already exist when Alembic runs.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_invoices"
down_revision: Union[str, None] = "0002_case_messages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    if "invoices" not in existing:
        op.create_table(
            "invoices",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("tenant_id", sa.Integer(), nullable=False, index=True),
            sa.Column(
                "case_id",
                sa.Integer(),
                sa.ForeignKey("cases.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "client_id",
                sa.Integer(),
                sa.ForeignKey("clients.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "created_by_user_id",
                sa.Integer(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
                index=True,
            ),
            sa.Column("invoice_number", sa.String(), nullable=False, unique=True, index=True),
            sa.Column("description", sa.String(), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
            sa.Column("amount_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="outstanding", index=True),
            sa.Column("issued_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("payment_provider", sa.String(), nullable=True),
            sa.Column("payment_reference", sa.String(), nullable=True),
            sa.Column("payment_status", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    if "invoice_line_items" not in existing:
        op.create_table(
            "invoice_line_items",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column(
                "invoice_id",
                sa.Integer(),
                sa.ForeignKey("invoices.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("description", sa.String(), nullable=False),
            sa.Column("hours", sa.Numeric(8, 2), nullable=True),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())
    if "invoice_line_items" in existing:
        op.drop_table("invoice_line_items")
    if "invoices" in existing:
        op.drop_table("invoices")
