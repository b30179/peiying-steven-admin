"""Expand Phase 1 quote hierarchy for the S2 controlled comparison workflow."""

from alembic import op
import sqlalchemy as sa

revision = "20260716_0002"
down_revision = "20260716_0001"
branch_labels = None
depends_on = None


def add_tracking_columns(table_name: str, include_status: bool = True) -> None:
    if include_status:
        op.add_column(table_name, sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"))
    op.add_column(table_name, sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.add_column(table_name, sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.add_column(table_name, sa.Column("created_by", sa.String(length=100), nullable=False, server_default="migration"))
    op.add_column(table_name, sa.Column("updated_by", sa.String(length=100), nullable=False, server_default="migration"))


def drop_tracking_columns(table_name: str, include_status: bool = True) -> None:
    op.drop_column(table_name, "updated_by")
    op.drop_column(table_name, "created_by")
    op.drop_column(table_name, "updated_at")
    op.drop_column(table_name, "created_at")
    if include_status:
        op.drop_column(table_name, "status")


def upgrade() -> None:
    op.alter_column("steven_quote_jobs", "title", new_column_name="subject")
    op.add_column("steven_quote_jobs", sa.Column("recommended_supplier_id", sa.String(length=36), nullable=True))
    op.add_column("steven_quote_jobs", sa.Column("non_lowest_reason", sa.Text(), nullable=True))
    op.add_column("steven_quote_jobs", sa.Column("approval_opinion", sa.Text(), nullable=True))
    op.add_column("steven_quote_jobs", sa.Column("source_file_id", sa.String(length=36), nullable=True))
    add_tracking_columns("steven_quote_jobs", include_status=False)

    op.alter_column("steven_quote_items", "name", new_column_name="item")
    op.alter_column("steven_quote_items", "quantity", new_column_name="qty")
    op.drop_constraint("ck_steven_quote_items_quantity_positive", "steven_quote_items", type_="check")
    op.create_check_constraint("ck_steven_quote_items_qty_positive", "steven_quote_items", "qty > 0")
    op.add_column("steven_quote_items", sa.Column("item_code", sa.String(length=50), nullable=True))
    op.execute("UPDATE steven_quote_items SET item_code = id WHERE item_code IS NULL")
    op.alter_column("steven_quote_items", "item_code", nullable=False)
    op.add_column("steven_quote_items", sa.Column("specification", sa.String(length=500), nullable=False, server_default=""))
    op.add_column("steven_quote_items", sa.Column("unit", sa.String(length=30), nullable=False, server_default="件"))
    add_tracking_columns("steven_quote_items")
    op.create_unique_constraint("uq_steven_quote_items_job_code", "steven_quote_items", ["quote_job_id", "item_code"])

    op.add_column("steven_quote_suppliers", sa.Column("supplier_code", sa.String(length=50), nullable=True))
    op.execute("UPDATE steven_quote_suppliers SET supplier_code = id WHERE supplier_code IS NULL")
    op.alter_column("steven_quote_suppliers", "supplier_code", nullable=False)
    op.add_column("steven_quote_suppliers", sa.Column("valid_until", sa.Date(), nullable=False, server_default=sa.text("'2099-12-31'::date")))
    op.add_column("steven_quote_suppliers", sa.Column("subtotal", sa.Numeric(14, 2), nullable=False, server_default="0"))
    op.add_column("steven_quote_suppliers", sa.Column("total", sa.Numeric(14, 2), nullable=False, server_default="0"))
    op.add_column("steven_quote_suppliers", sa.Column("source_file_id", sa.String(length=36), nullable=True))
    add_tracking_columns("steven_quote_suppliers")
    op.create_check_constraint("ck_steven_quote_suppliers_subtotal_nonnegative", "steven_quote_suppliers", "subtotal >= 0")
    op.create_check_constraint("ck_steven_quote_suppliers_total_nonnegative", "steven_quote_suppliers", "total >= 0")
    op.create_unique_constraint("uq_steven_quote_suppliers_job_code", "steven_quote_suppliers", ["quote_job_id", "supplier_code"])
    op.create_unique_constraint("uq_steven_quote_suppliers_job_name", "steven_quote_suppliers", ["quote_job_id", "supplier_name"])

    op.add_column("steven_quote_offer_lines", sa.Column("line_total", sa.Numeric(14, 2), nullable=False, server_default="0"))
    op.add_column("steven_quote_offer_lines", sa.Column("remark", sa.Text(), nullable=False, server_default=""))
    add_tracking_columns("steven_quote_offer_lines")
    op.create_check_constraint("ck_steven_quote_offer_lines_total_nonnegative", "steven_quote_offer_lines", "line_total >= 0")

    op.create_foreign_key(
        "fk_steven_quote_jobs_recommended_supplier",
        "steven_quote_jobs",
        "steven_quote_suppliers",
        ["recommended_supplier_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "steven_quote_import_batches",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("quote_job_id", sa.String(length=36), sa.ForeignKey("steven_quote_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="prechecked"),
        sa.Column("issue_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.String(length=100), nullable=False),
    )
    op.create_table(
        "steven_quote_approvals",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("quote_job_id", sa.String(length=36), sa.ForeignKey("steven_quote_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("submitted_by", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("opinion", sa.Text(), nullable=True),
        sa.Column("decided_by", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "steven_quote_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("quote_job_id", sa.String(length=36), sa.ForeignKey("steven_quote_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.String(length=100), nullable=False),
        sa.CheckConstraint("version_number > 0", name="ck_steven_quote_versions_positive"),
        sa.UniqueConstraint("quote_job_id", "version_number", name="uq_steven_quote_versions_job_version"),
    )
    op.create_index("ix_steven_quote_suppliers_valid_until", "steven_quote_suppliers", ["valid_until"])
    op.create_index("ix_steven_quote_jobs_status", "steven_quote_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_steven_quote_jobs_status", table_name="steven_quote_jobs")
    op.drop_index("ix_steven_quote_suppliers_valid_until", table_name="steven_quote_suppliers")
    op.drop_table("steven_quote_versions")
    op.drop_table("steven_quote_approvals")
    op.drop_table("steven_quote_import_batches")
    op.drop_constraint("fk_steven_quote_jobs_recommended_supplier", "steven_quote_jobs", type_="foreignkey")

    op.drop_constraint("ck_steven_quote_offer_lines_total_nonnegative", "steven_quote_offer_lines", type_="check")
    drop_tracking_columns("steven_quote_offer_lines")
    op.drop_column("steven_quote_offer_lines", "remark")
    op.drop_column("steven_quote_offer_lines", "line_total")

    op.drop_constraint("uq_steven_quote_suppliers_job_name", "steven_quote_suppliers", type_="unique")
    op.drop_constraint("uq_steven_quote_suppliers_job_code", "steven_quote_suppliers", type_="unique")
    op.drop_constraint("ck_steven_quote_suppliers_total_nonnegative", "steven_quote_suppliers", type_="check")
    op.drop_constraint("ck_steven_quote_suppliers_subtotal_nonnegative", "steven_quote_suppliers", type_="check")
    drop_tracking_columns("steven_quote_suppliers")
    op.drop_column("steven_quote_suppliers", "source_file_id")
    op.drop_column("steven_quote_suppliers", "total")
    op.drop_column("steven_quote_suppliers", "subtotal")
    op.drop_column("steven_quote_suppliers", "valid_until")
    op.drop_column("steven_quote_suppliers", "supplier_code")

    op.drop_constraint("uq_steven_quote_items_job_code", "steven_quote_items", type_="unique")
    drop_tracking_columns("steven_quote_items")
    op.drop_column("steven_quote_items", "unit")
    op.drop_column("steven_quote_items", "specification")
    op.drop_column("steven_quote_items", "item_code")
    op.drop_constraint("ck_steven_quote_items_qty_positive", "steven_quote_items", type_="check")
    op.alter_column("steven_quote_items", "qty", new_column_name="quantity")
    op.alter_column("steven_quote_items", "item", new_column_name="name")
    op.create_check_constraint("ck_steven_quote_items_quantity_positive", "steven_quote_items", "quantity > 0")

    drop_tracking_columns("steven_quote_jobs", include_status=False)
    op.drop_column("steven_quote_jobs", "source_file_id")
    op.drop_column("steven_quote_jobs", "approval_opinion")
    op.drop_column("steven_quote_jobs", "non_lowest_reason")
    op.drop_column("steven_quote_jobs", "recommended_supplier_id")
    op.alter_column("steven_quote_jobs", "subject", new_column_name="title")