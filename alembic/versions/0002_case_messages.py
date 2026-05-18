"""case_messages table (client <-> lawyer messaging)

Revision ID: 0002_case_messages
Revises: 0001_baseline
Create Date: 2026-05-17 00:00:00.000000

Idempotent on purpose: most environments bootstrap the schema via
``Base.metadata.create_all`` (schema_sync path), so the table may already
exist by the time Alembic runs. We only create it when missing.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_case_messages"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "case_messages" in inspector.get_table_names():
        return

    op.create_table(
        "case_messages",
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
            "portal_account_id",
            sa.Integer(),
            sa.ForeignKey("client_portal_accounts.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "sender_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("sender_role", sa.String(length=16), nullable=False, index=True),
        sa.Column("sender_name", sa.String(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("attachment_filename", sa.String(), nullable=True),
        sa.Column("attachment_path", sa.String(), nullable=True),
        sa.Column("attachment_content_type", sa.String(), nullable=True),
        sa.Column("attachment_size", sa.BigInteger(), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            index=True,
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "case_messages" in inspector.get_table_names():
        op.drop_table("case_messages")
