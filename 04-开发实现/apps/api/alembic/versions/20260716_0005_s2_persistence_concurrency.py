"""Add persistent S2 transactions, audit and append-only file versions."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260716_0005"
down_revision = "20260716_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("steven_quote_jobs", sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("steven_quote_jobs", sa.Column("demo_label", sa.Text(), nullable=True))
    op.add_column("steven_quote_jobs", sa.Column("approval_id", sa.String(length=36), nullable=True))
    op.add_column("steven_quote_jobs", sa.Column("next_export_version", sa.Integer(), nullable=False, server_default="1"))
    op.create_check_constraint("ck_steven_quote_jobs_status", "steven_quote_jobs", "status IN ('draft','incomplete','ready_for_review','pending_approval','approved','exported')")
    op.create_check_constraint("ck_steven_quote_jobs_next_export_version", "steven_quote_jobs", "next_export_version > 0")
    op.create_foreign_key("fk_steven_quote_jobs_approval", "steven_quote_jobs", "steven_quote_approvals", ["approval_id"], ["id"], ondelete="SET NULL")

    op.add_column("steven_quote_import_batches", sa.Column("valid", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("steven_quote_import_batches", sa.Column("payload_sha256", sa.String(length=64), nullable=False, server_default="0" * 64))
    op.alter_column("steven_quote_import_batches", "payload_sha256", server_default=None)
    op.add_column("steven_quote_import_batches", sa.Column("issues", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("steven_quote_import_batches", sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("steven_quote_import_batches", sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("steven_quote_import_batches", sa.Column("confirmed_by", sa.String(length=36), nullable=True))
    op.add_column("steven_quote_import_batches", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.add_column("steven_quote_import_batches", sa.Column("updated_by", sa.String(length=36), nullable=False, server_default="migration"))
    op.create_check_constraint("ck_steven_quote_import_batches_status", "steven_quote_import_batches", "status IN ('prechecked','confirmed','rejected')")
    op.create_foreign_key("fk_steven_quote_import_batches_confirmed_by", "steven_quote_import_batches", "users", ["confirmed_by"], ["id"], ondelete="SET NULL")
    op.create_index("ix_steven_quote_import_batches_job_status", "steven_quote_import_batches", ["quote_job_id", "status"])

    op.add_column("steven_quote_approvals", sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.add_column("steven_quote_approvals", sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint("ck_steven_quote_approvals_status", "steven_quote_approvals", "status IN ('pending','approved','rejected')")
    op.execute("ALTER TABLE steven_quote_approvals ADD CONSTRAINT fk_steven_quote_approvals_submitted_by FOREIGN KEY (submitted_by) REFERENCES users(id) ON DELETE RESTRICT NOT VALID")
    op.execute("ALTER TABLE steven_quote_approvals ADD CONSTRAINT fk_steven_quote_approvals_decided_by FOREIGN KEY (decided_by) REFERENCES users(id) ON DELETE RESTRICT NOT VALID")
    op.create_index("uq_steven_quote_approvals_one_pending", "steven_quote_approvals", ["quote_job_id"], unique=True, postgresql_where=sa.text("status = 'pending'"))
    op.create_index("ix_steven_quote_approvals_status_time", "steven_quote_approvals", ["status", "submitted_at"])

    op.alter_column("steven_quote_versions", "sha256", existing_type=sa.String(length=64), nullable=True)
    op.add_column("steven_quote_versions", sa.Column("object_type", sa.String(length=50), nullable=False, server_default="steven_quote_job"))
    op.add_column("steven_quote_versions", sa.Column("object_id", sa.String(length=36), nullable=True))
    op.execute("UPDATE steven_quote_versions SET object_id = quote_job_id WHERE object_id IS NULL")
    op.alter_column("steven_quote_versions", "object_id", nullable=False)
    op.add_column("steven_quote_versions", sa.Column("status", sa.String(length=32), nullable=False, server_default="ready"))
    op.add_column("steven_quote_versions", sa.Column("mime_type", sa.String(length=150), nullable=False, server_default="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
    op.add_column("steven_quote_versions", sa.Column("size_bytes", sa.BigInteger(), nullable=True))
    op.add_column("steven_quote_versions", sa.Column("failure_reason", sa.Text(), nullable=True))
    op.add_column("steven_quote_versions", sa.Column("temporary_storage_key", sa.String(length=500), nullable=True))
    op.add_column("steven_quote_versions", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("steven_quote_versions", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_check_constraint("ck_steven_quote_versions_status", "steven_quote_versions", "status IN ('reserved','ready','failed')")
    op.create_check_constraint("ck_steven_quote_versions_size", "steven_quote_versions", "size_bytes IS NULL OR size_bytes >= 0")
    op.create_unique_constraint("uq_steven_quote_versions_storage_key", "steven_quote_versions", ["storage_key"])
    op.create_index("ix_steven_quote_versions_status_time", "steven_quote_versions", ["status", "created_at"])

    op.create_table(
        "steven_quote_audit_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("actor_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("object_type", sa.String(length=100), nullable=False),
        sa.Column("object_id", sa.String(length=36), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("request_id", sa.String(length=100), nullable=True),
        sa.Column("before_after", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_steven_quote_audit_object_time", "steven_quote_audit_events", ["object_id", "occurred_at"])
    op.create_index("ix_steven_quote_audit_actor_time", "steven_quote_audit_events", ["actor_user_id", "occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_steven_quote_audit_actor_time", table_name="steven_quote_audit_events")
    op.drop_index("ix_steven_quote_audit_object_time", table_name="steven_quote_audit_events")
    op.drop_table("steven_quote_audit_events")
    op.drop_index("ix_steven_quote_versions_status_time", table_name="steven_quote_versions")
    op.drop_constraint("uq_steven_quote_versions_storage_key", "steven_quote_versions", type_="unique")
    op.drop_constraint("ck_steven_quote_versions_size", "steven_quote_versions", type_="check")
    op.drop_constraint("ck_steven_quote_versions_status", "steven_quote_versions", type_="check")
    for column in ["updated_at", "published_at", "temporary_storage_key", "failure_reason", "size_bytes", "mime_type", "status", "object_id", "object_type"]:
        op.drop_column("steven_quote_versions", column)
    op.alter_column("steven_quote_versions", "sha256", existing_type=sa.String(length=64), nullable=False)
    op.drop_index("ix_steven_quote_approvals_status_time", table_name="steven_quote_approvals")
    op.drop_index("uq_steven_quote_approvals_one_pending", table_name="steven_quote_approvals")
    op.drop_constraint("fk_steven_quote_approvals_decided_by", "steven_quote_approvals", type_="foreignkey")
    op.drop_constraint("fk_steven_quote_approvals_submitted_by", "steven_quote_approvals", type_="foreignkey")
    op.drop_constraint("ck_steven_quote_approvals_status", "steven_quote_approvals", type_="check")
    op.drop_column("steven_quote_approvals", "decided_at")
    op.drop_column("steven_quote_approvals", "submitted_at")
    op.drop_index("ix_steven_quote_import_batches_job_status", table_name="steven_quote_import_batches")
    op.drop_constraint("fk_steven_quote_import_batches_confirmed_by", "steven_quote_import_batches", type_="foreignkey")
    op.drop_constraint("ck_steven_quote_import_batches_status", "steven_quote_import_batches", type_="check")
    for column in ["updated_by", "updated_at", "confirmed_by", "confirmed_at", "payload", "issues", "payload_sha256", "valid"]:
        op.drop_column("steven_quote_import_batches", column)
    op.drop_constraint("fk_steven_quote_jobs_approval", "steven_quote_jobs", type_="foreignkey")
    op.drop_constraint("ck_steven_quote_jobs_next_export_version", "steven_quote_jobs", type_="check")
    op.drop_constraint("ck_steven_quote_jobs_status", "steven_quote_jobs", type_="check")
    for column in ["next_export_version", "approval_id", "demo_label", "is_demo"]:
        op.drop_column("steven_quote_jobs", column)
