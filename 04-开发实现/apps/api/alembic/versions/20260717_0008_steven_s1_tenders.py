"""Add Steven S1 tender/document workflow."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260717_0008"
down_revision = "20260717_0007"
branch_labels = None
depends_on = None

PERMISSIONS = [
    ("perm-tenders-read", "steven:tenders:read", "读取标书与文书事项"),
    ("perm-tenders-write", "steven:tenders:write", "创建及修订标书与文书事项"),
    ("perm-tenders-submit", "steven:tenders:submit", "提交标书与文书审批"),
    ("perm-tenders-approve", "steven:tenders:approve", "批准或退回标书与文书"),
    ("perm-tenders-export", "steven:tenders:export", "导出已批准标书与文书"),
    ("perm-tenders-audit-scoped", "steven:tenders:audit:read_scoped", "读取标书与文书事项审计"),
]


def upgrade() -> None:
    permission_table = sa.table(
        "permissions",
        sa.column("id", sa.String),
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("module", sa.String),
    )
    role_permission_table = sa.table(
        "role_permissions",
        sa.column("role_id", sa.String),
        sa.column("permission_id", sa.String),
    )
    op.bulk_insert(
        permission_table,
        [{"id": item[0], "code": item[1], "name": item[2], "module": "steven"} for item in PERMISSIONS],
    )
    op.bulk_insert(
        role_permission_table,
        [
            *[
                {"role_id": "role-steven", "permission_id": permission_id}
                for permission_id in (
                    "perm-tenders-read",
                    "perm-tenders-write",
                    "perm-tenders-submit",
                    "perm-tenders-export",
                    "perm-tenders-audit-scoped",
                )
            ],
            *[
                {"role_id": "role-approver", "permission_id": permission_id}
                for permission_id in (
                    "perm-tenders-read",
                    "perm-tenders-approve",
                    "perm-tenders-audit-scoped",
                )
            ],
        ],
    )

    op.create_table(
        "steven_templates",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("document_type", sa.String(length=100), nullable=False),
        sa.Column("template_body", sa.Text(), nullable=False),
        sa.Column("variables", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("version > 0", name="ck_steven_templates_version"),
        sa.CheckConstraint("status IN ('active','inactive')", name="ck_steven_templates_status"),
        sa.UniqueConstraint("code", "version", name="uq_steven_templates_code_version"),
    )
    op.create_index("ix_steven_templates_status_name", "steven_templates", ["status", "name"])

    op.create_table(
        "steven_tender_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("template_id", sa.String(length=36), sa.ForeignKey("steven_templates.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(length=250), nullable=False),
        sa.Column("document_number", sa.String(length=100), nullable=False),
        sa.Column("subject", sa.String(length=250), nullable=False),
        sa.Column("generated_date", sa.Date(), nullable=False),
        sa.Column("deadline_date", sa.Date(), nullable=False),
        sa.Column("budget_min", sa.Numeric(14, 2), nullable=False),
        sa.Column("budget_max", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="HKD"),
        sa.Column("location", sa.String(length=300), nullable=False),
        sa.Column("controlled_clauses", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("rendered_body", sa.Text(), nullable=True),
        sa.Column("unresolved_variables", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("next_export_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("submitted_by", sa.String(length=36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(length=36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_opinion", sa.Text(), nullable=True),
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_by", sa.String(length=36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('draft','draft_error','submitted','approved','returned')", name="ck_steven_tender_jobs_status"),
        sa.CheckConstraint("deadline_date >= generated_date + 3", name="ck_steven_tender_jobs_deadline"),
        sa.CheckConstraint("budget_min >= 0 AND budget_max >= 0 AND budget_min <= budget_max", name="ck_steven_tender_jobs_budget"),
        sa.CheckConstraint("currency = upper(currency)", name="ck_steven_tender_jobs_currency"),
        sa.CheckConstraint("next_export_version > 0", name="ck_steven_tender_jobs_next_export_version"),
        sa.UniqueConstraint("document_number", name="uq_steven_tender_jobs_document_number"),
    )
    op.create_index("ix_steven_tender_jobs_status_updated", "steven_tender_jobs", ["status", "updated_at"])
    op.create_index("ix_steven_tender_jobs_template", "steven_tender_jobs", ["template_id"])

    op.create_table(
        "steven_tender_suppliers",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tender_job_id", sa.String(length=36), sa.ForeignKey("steven_tender_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("supplier_name", sa.String(length=250), nullable=False),
        sa.Column("normalized_name", sa.String(length=250), nullable=False),
        sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tender_job_id", "normalized_name", name="uq_steven_tender_supplier_name"),
    )
    op.create_index("ix_steven_tender_suppliers_job", "steven_tender_suppliers", ["tender_job_id", "created_at"])

    op.create_table(
        "steven_tender_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tender_job_id", sa.String(length=36), sa.ForeignKey("steven_tender_jobs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("file_id", sa.String(length=36), sa.ForeignKey("files.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=150), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("temporary_storage_key", sa.String(length=500), nullable=True),
        sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("version_number > 0", name="ck_steven_tender_versions_number"),
        sa.CheckConstraint("status IN ('reserved','ready','failed')", name="ck_steven_tender_versions_status"),
        sa.CheckConstraint("size_bytes IS NULL OR size_bytes >= 0", name="ck_steven_tender_versions_size"),
        sa.UniqueConstraint("tender_job_id", "version_number", name="uq_steven_tender_versions_job_version"),
        sa.UniqueConstraint("storage_key", name="uq_steven_tender_versions_storage_key"),
    )
    op.create_index("ix_steven_tender_versions_job_status", "steven_tender_versions", ["tender_job_id", "status", "version_number"])

    op.create_table(
        "steven_tender_candidate_links",
        sa.Column("candidate_id", sa.String(length=36), sa.ForeignKey("review_candidates.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("tender_job_id", sa.String(length=36), sa.ForeignKey("steven_tender_jobs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("candidate_kind", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("candidate_kind IN ('tender_source_extraction','clause_draft')", name="ck_steven_tender_candidate_kind"),
    )
    op.create_index("ix_steven_tender_candidate_links_job", "steven_tender_candidate_links", ["tender_job_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_steven_tender_candidate_links_job", table_name="steven_tender_candidate_links")
    op.drop_table("steven_tender_candidate_links")
    op.drop_index("ix_steven_tender_versions_job_status", table_name="steven_tender_versions")
    op.drop_table("steven_tender_versions")
    op.drop_index("ix_steven_tender_suppliers_job", table_name="steven_tender_suppliers")
    op.drop_table("steven_tender_suppliers")
    op.drop_index("ix_steven_tender_jobs_template", table_name="steven_tender_jobs")
    op.drop_index("ix_steven_tender_jobs_status_updated", table_name="steven_tender_jobs")
    op.drop_table("steven_tender_jobs")
    op.drop_index("ix_steven_templates_status_name", table_name="steven_templates")
    op.drop_table("steven_templates")
    for role_id, permission_ids in (
        ("role-steven", ("perm-tenders-read", "perm-tenders-write", "perm-tenders-submit", "perm-tenders-export", "perm-tenders-audit-scoped")),
        ("role-approver", ("perm-tenders-read", "perm-tenders-approve", "perm-tenders-audit-scoped")),
    ):
        for permission_id in permission_ids:
            op.execute(
                sa.text(
                    "DELETE FROM role_permissions "
                    "WHERE role_id=:role_id AND permission_id=:permission_id"
                ).bindparams(role_id=role_id, permission_id=permission_id)
            )
    op.execute("DELETE FROM permissions WHERE id LIKE 'perm-tenders-%'")
