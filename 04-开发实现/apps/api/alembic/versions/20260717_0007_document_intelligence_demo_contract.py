"""Add reusable document intelligence and review candidate contract."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260717_0007"
down_revision = "20260716_0006"
branch_labels = None
depends_on = None

JOB_STATES = "('pending','running','needs_review','confirmed','rejected','failed')"


def _job_table(name: str) -> None:
    op.create_table(
        name,
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("file_id", sa.String(length=36), sa.ForeignKey("files.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("module", sa.String(length=50), nullable=False),
        sa.Column("document_type", sa.String(length=100), nullable=False),
        sa.Column("purpose", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=150), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("request_id", sa.String(length=100), nullable=False),
        sa.Column("output_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(f"status IN {JOB_STATES}", name=f"ck_{name}_status"),
    )
    op.create_index(f"ix_{name}_file_time", name, ["file_id", "created_at"])
    op.create_index(f"ix_{name}_request", name, ["request_id"])
    op.create_index(f"ix_{name}_route_status", name, ["module", "document_type", "purpose", "status"])


def upgrade() -> None:
    op.create_table(
        "files",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("module", sa.String(length=50), nullable=False),
        sa.Column("document_type", sa.String(length=100), nullable=False),
        sa.Column("purpose", sa.String(length=100), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=150), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("request_id", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("size_bytes >= 0", name="ck_files_size"),
        sa.CheckConstraint("status IN ('stored','failed')", name="ck_files_status"),
        sa.UniqueConstraint("storage_key", name="uq_files_storage_key"),
    )
    op.create_index("ix_files_sha256", "files", ["sha256"])
    op.create_index("ix_files_request", "files", ["request_id"])
    op.create_index("ix_files_route_time", "files", ["module", "document_type", "purpose", "created_at"])

    _job_table("ocr_jobs")
    _job_table("ai_jobs")

    op.create_table(
        "review_candidates",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_file_id", sa.String(length=36), sa.ForeignKey("files.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("ocr_job_id", sa.String(length=36), sa.ForeignKey("ocr_jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ai_job_id", sa.String(length=36), sa.ForeignKey("ai_jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("module", sa.String(length=50), nullable=False),
        sa.Column("document_type", sa.String(length=100), nullable=False),
        sa.Column("purpose", sa.String(length=100), nullable=False),
        sa.Column("schema_name", sa.String(length=150), nullable=False),
        sa.Column("schema_version", sa.String(length=30), nullable=False),
        sa.Column("provider", sa.String(length=200), nullable=False),
        sa.Column("model", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("candidate_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("human_revision_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("reviewer_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("target_object_type", sa.String(length=100), nullable=True),
        sa.Column("target_object_id", sa.String(length=36), nullable=True),
        sa.Column("request_id", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"status IN {JOB_STATES}", name="ck_review_candidates_status"),
    )
    op.create_index("ix_review_candidates_request", "review_candidates", ["request_id"])
    op.create_index("ix_review_candidates_route_status", "review_candidates", ["module", "document_type", "purpose", "status"])
    op.create_index("ix_review_candidates_target_time", "review_candidates", ["target_object_type", "target_object_id", "created_at"])

    op.create_table(
        "steven_quote_import_candidates",
        sa.Column("candidate_id", sa.String(length=36), sa.ForeignKey("review_candidates.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("quote_job_id", sa.String(length=36), sa.ForeignKey("steven_quote_jobs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_steven_quote_import_candidates_job", "steven_quote_import_candidates", ["quote_job_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_steven_quote_import_candidates_job", table_name="steven_quote_import_candidates")
    op.drop_table("steven_quote_import_candidates")
    op.drop_index("ix_review_candidates_target_time", table_name="review_candidates")
    op.drop_index("ix_review_candidates_route_status", table_name="review_candidates")
    op.drop_index("ix_review_candidates_request", table_name="review_candidates")
    op.drop_table("review_candidates")
    for name in ("ai_jobs", "ocr_jobs"):
        op.drop_index(f"ix_{name}_route_status", table_name=name)
        op.drop_index(f"ix_{name}_request", table_name=name)
        op.drop_index(f"ix_{name}_file_time", table_name=name)
        op.drop_table(name)
    op.drop_index("ix_files_route_time", table_name="files")
    op.drop_index("ix_files_request", table_name="files")
    op.drop_index("ix_files_sha256", table_name="files")
    op.drop_table("files")
