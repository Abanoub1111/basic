"""Create email processing records.

Revision ID: 20260907_01
Revises:
Create Date: 2026-09-07
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260907_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_processing_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("author", sa.String(length=320), nullable=False),
        sa.Column("recipient", sa.String(length=320), nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("email_thread", sa.Text(), nullable=False),
        sa.Column("classification", sa.String(length=20), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("action", sa.String(length=30), nullable=True),
        sa.Column("reply_recipient", sa.String(length=320), nullable=True),
        sa.Column("reply_subject", sa.String(length=500), nullable=True),
        sa.Column("reply_content", sa.Text(), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_email_processing_records_created_at",
        "email_processing_records",
        ["created_at"],
    )
    op.create_index(
        "ix_email_processing_records_status",
        "email_processing_records",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_email_processing_records_status",
        table_name="email_processing_records",
    )
    op.drop_index(
        "ix_email_processing_records_created_at",
        table_name="email_processing_records",
    )
    op.drop_table("email_processing_records")
