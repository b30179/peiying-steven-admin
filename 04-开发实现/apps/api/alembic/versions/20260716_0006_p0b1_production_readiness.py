"""Add case-insensitive usernames and persistent platform audit."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260716_0006"
down_revision = "20260716_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$
        DECLARE conflict_report text;
        BEGIN
            SELECT string_agg(normalized_username || ' => [' || usernames || ']', '; ' ORDER BY normalized_username)
              INTO conflict_report
              FROM (
                    SELECT lower(username) AS normalized_username,
                           string_agg(username, ', ' ORDER BY username) AS usernames
                      FROM users
                     GROUP BY lower(username)
                    HAVING count(*) > 1
              ) conflicts;
            IF conflict_report IS NOT NULL THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23505',
                    MESSAGE = 'case-insensitive username conflicts must be governed before migration: ' || conflict_report;
            END IF;
        END $$;
    """)
    op.create_index("uq_users_username_lower", "users", [sa.text("lower(username)")], unique=True)
    op.create_table(
        "platform_audit_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("actor_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor_label", sa.String(length=200), nullable=True),
        sa.Column("action", sa.String(length=150), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("object_type", sa.String(length=100), nullable=False),
        sa.Column("object_id", sa.String(length=100), nullable=False),
        sa.Column("request_id", sa.String(length=100), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("before_after", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.CheckConstraint("outcome IN ('success','rejected','failed')", name="ck_platform_audit_events_outcome"),
    )
    op.create_index("ix_platform_audit_request_time", "platform_audit_events", ["request_id", "occurred_at"])
    op.create_index("ix_platform_audit_object_time", "platform_audit_events", ["object_type", "object_id", "occurred_at"])
    op.create_index("ix_platform_audit_actor_time", "platform_audit_events", ["actor_user_id", "occurred_at"])
    op.create_index("ix_platform_audit_action_time", "platform_audit_events", ["action", "occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_platform_audit_action_time", table_name="platform_audit_events")
    op.drop_index("ix_platform_audit_actor_time", table_name="platform_audit_events")
    op.drop_index("ix_platform_audit_object_time", table_name="platform_audit_events")
    op.drop_index("ix_platform_audit_request_time", table_name="platform_audit_events")
    op.drop_table("platform_audit_events")
    op.drop_index("uq_users_username_lower", table_name="users")
