"""Add persistent P0-A.1 authentication security events."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260716_0004"
down_revision = "20260716_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_security_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("subject_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.CheckConstraint("outcome IN ('success','rejected','failed')", name="ck_auth_security_events_outcome"),
    )
    op.create_index("ix_auth_security_events_type_time", "auth_security_events", ["event_type", "occurred_at"])
    op.create_index("ix_auth_security_events_subject_time", "auth_security_events", ["subject_user_id", "occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_auth_security_events_subject_time", table_name="auth_security_events")
    op.drop_index("ix_auth_security_events_type_time", table_name="auth_security_events")
    op.drop_table("auth_security_events")
