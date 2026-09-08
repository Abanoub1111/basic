"""Users, revocable sessions, and history ownership."""
from alembic import op
import sqlalchemy as sa

revision = "20260908_01"
down_revision = "20260907_01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("auth_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.add_column("email_processing_records", sa.Column("owner_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_history_owner", "email_processing_records", "users", ["owner_id"], ["id"])
    op.create_index("ix_email_processing_records_owner_id", "email_processing_records", ["owner_id"])


def downgrade():
    op.drop_index("ix_email_processing_records_owner_id", table_name="email_processing_records")
    op.drop_constraint("fk_history_owner", "email_processing_records", type_="foreignkey")
    op.drop_column("email_processing_records", "owner_id")
    op.drop_table("auth_sessions")
    op.drop_table("users")
