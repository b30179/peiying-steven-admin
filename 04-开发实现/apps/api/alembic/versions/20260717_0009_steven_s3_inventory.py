"""Add Steven S3 consumables inventory workflow."""

from alembic import op
import sqlalchemy as sa


revision = "20260717_0009"
down_revision = "20260717_0008"
branch_labels = None
depends_on = None

PERMISSIONS = [
    ("perm-inventory-read", "steven:inventory:read", "读取消耗品库存与盘点"),
    ("perm-inventory-write", "steven:inventory:write", "维护消耗品库存品项"),
    ("perm-inventory-count", "steven:inventory:count", "创建及修订消耗品盘点"),
    ("perm-inventory-submit", "steven:inventory:submit", "提交消耗品盘点审批"),
    ("perm-inventory-approve", "steven:inventory:approve", "批准或退回消耗品盘点"),
    ("perm-inventory-export", "steven:inventory:export", "导出已批准消耗品盘点"),
    ("perm-inventory-audit-scoped", "steven:inventory:audit:read_scoped", "读取消耗品盘点事项审计"),
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
                    "perm-inventory-read",
                    "perm-inventory-write",
                    "perm-inventory-count",
                    "perm-inventory-submit",
                    "perm-inventory-export",
                    "perm-inventory-audit-scoped",
                )
            ],
            *[
                {"role_id": "role-approver", "permission_id": permission_id}
                for permission_id in (
                    "perm-inventory-read",
                    "perm-inventory-approve",
                    "perm-inventory-audit-scoped",
                )
            ],
        ],
    )

    op.create_table(
        "steven_inventory_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("sku", sa.String(length=120), nullable=False),
        sa.Column("normalized_sku", sa.String(length=120), nullable=False),
        sa.Column("item_name", sa.String(length=250), nullable=False),
        sa.Column("category", sa.String(length=150), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=False),
        sa.Column("book_quantity", sa.Integer(), nullable=False),
        sa.Column("safety_stock", sa.Integer(), nullable=False),
        sa.Column("target_stock", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_by", sa.String(length=36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("book_quantity >= 0", name="ck_steven_inventory_items_book_quantity"),
        sa.CheckConstraint("safety_stock >= 0", name="ck_steven_inventory_items_safety_stock"),
        sa.CheckConstraint("target_stock >= safety_stock", name="ck_steven_inventory_items_target_stock"),
        sa.CheckConstraint("status IN ('active','inactive')", name="ck_steven_inventory_items_status"),
        sa.UniqueConstraint("normalized_sku", name="uq_steven_inventory_items_normalized_sku"),
    )
    op.create_index(
        "ix_steven_inventory_items_status_location",
        "steven_inventory_items",
        ["status", "location", "item_name"],
    )

    op.create_table(
        "steven_inventory_counts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("count_number", sa.String(length=120), nullable=False),
        sa.Column("count_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
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
        sa.CheckConstraint("status IN ('draft','submitted','approved','returned')", name="ck_steven_inventory_counts_status"),
        sa.CheckConstraint("next_export_version > 0", name="ck_steven_inventory_counts_next_export_version"),
        sa.UniqueConstraint("count_number", name="uq_steven_inventory_counts_number"),
    )
    op.create_index(
        "ix_steven_inventory_counts_status_updated",
        "steven_inventory_counts",
        ["status", "updated_at"],
    )

    op.create_table(
        "steven_inventory_count_lines",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("inventory_count_id", sa.String(length=36), sa.ForeignKey("steven_inventory_counts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("inventory_item_id", sa.String(length=36), sa.ForeignKey("steven_inventory_items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("sku_snapshot", sa.String(length=120), nullable=False),
        sa.Column("item_name_snapshot", sa.String(length=250), nullable=False),
        sa.Column("location_snapshot", sa.String(length=200), nullable=False),
        sa.Column("book_quantity_snapshot", sa.Integer(), nullable=False),
        sa.Column("safety_stock_snapshot", sa.Integer(), nullable=False),
        sa.Column("target_stock_snapshot", sa.Integer(), nullable=False),
        sa.Column("counted_quantity", sa.Integer(), nullable=False),
        sa.Column("difference_quantity", sa.Integer(), nullable=False),
        sa.Column("is_low_stock", sa.Boolean(), nullable=False),
        sa.Column("suggested_order_quantity", sa.Integer(), nullable=False),
        sa.Column("confirmed_order_quantity", sa.Integer(), nullable=False),
        sa.Column("manual_reason", sa.Text(), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.String(length=36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("book_quantity_snapshot >= 0", name="ck_steven_inventory_lines_book_quantity"),
        sa.CheckConstraint("safety_stock_snapshot >= 0", name="ck_steven_inventory_lines_safety_stock"),
        sa.CheckConstraint("target_stock_snapshot >= safety_stock_snapshot", name="ck_steven_inventory_lines_target_stock"),
        sa.CheckConstraint("counted_quantity >= 0", name="ck_steven_inventory_lines_counted_quantity"),
        sa.CheckConstraint("suggested_order_quantity >= 0", name="ck_steven_inventory_lines_suggested_order"),
        sa.CheckConstraint("confirmed_order_quantity >= 0", name="ck_steven_inventory_lines_confirmed_order"),
        sa.CheckConstraint(
            "confirmed_order_quantity = suggested_order_quantity OR length(btrim(coalesce(manual_reason,''))) > 0",
            name="ck_steven_inventory_lines_manual_reason",
        ),
        sa.UniqueConstraint(
            "inventory_count_id",
            "inventory_item_id",
            name="uq_steven_inventory_count_item",
        ),
    )
    op.create_index(
        "ix_steven_inventory_count_lines_count",
        "steven_inventory_count_lines",
        ["inventory_count_id", "created_at"],
    )
    op.create_index(
        "ix_steven_inventory_count_lines_low_stock",
        "steven_inventory_count_lines",
        ["is_low_stock", "inventory_item_id"],
    )

    op.create_table(
        "steven_inventory_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("inventory_count_id", sa.String(length=36), sa.ForeignKey("steven_inventory_counts.id", ondelete="RESTRICT"), nullable=False),
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
        sa.CheckConstraint("version_number > 0", name="ck_steven_inventory_versions_number"),
        sa.CheckConstraint("status IN ('reserved','ready','failed')", name="ck_steven_inventory_versions_status"),
        sa.CheckConstraint("size_bytes IS NULL OR size_bytes >= 0", name="ck_steven_inventory_versions_size"),
        sa.UniqueConstraint(
            "inventory_count_id",
            "version_number",
            name="uq_steven_inventory_versions_count_version",
        ),
        sa.UniqueConstraint("storage_key", name="uq_steven_inventory_versions_storage_key"),
    )
    op.create_index(
        "ix_steven_inventory_versions_count_status",
        "steven_inventory_versions",
        ["inventory_count_id", "status", "version_number"],
    )

    op.create_table(
        "steven_inventory_candidate_links",
        sa.Column("candidate_id", sa.String(length=36), sa.ForeignKey("review_candidates.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("inventory_count_id", sa.String(length=36), sa.ForeignKey("steven_inventory_counts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("candidate_kind", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "candidate_kind IN ('inventory_sheet_extraction','inventory_exception_explanation')",
            name="ck_steven_inventory_candidate_kind",
        ),
    )
    op.create_index(
        "ix_steven_inventory_candidate_links_count",
        "steven_inventory_candidate_links",
        ["inventory_count_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_steven_inventory_candidate_links_count", table_name="steven_inventory_candidate_links")
    op.drop_table("steven_inventory_candidate_links")
    op.drop_index("ix_steven_inventory_versions_count_status", table_name="steven_inventory_versions")
    op.drop_table("steven_inventory_versions")
    op.drop_index("ix_steven_inventory_count_lines_low_stock", table_name="steven_inventory_count_lines")
    op.drop_index("ix_steven_inventory_count_lines_count", table_name="steven_inventory_count_lines")
    op.drop_table("steven_inventory_count_lines")
    op.drop_index("ix_steven_inventory_counts_status_updated", table_name="steven_inventory_counts")
    op.drop_table("steven_inventory_counts")
    op.drop_index("ix_steven_inventory_items_status_location", table_name="steven_inventory_items")
    op.drop_table("steven_inventory_items")
    for role_id, permission_ids in (
        (
            "role-steven",
            (
                "perm-inventory-read",
                "perm-inventory-write",
                "perm-inventory-count",
                "perm-inventory-submit",
                "perm-inventory-export",
                "perm-inventory-audit-scoped",
            ),
        ),
        (
            "role-approver",
            ("perm-inventory-read", "perm-inventory-approve", "perm-inventory-audit-scoped"),
        ),
    ):
        for permission_id in permission_ids:
            op.execute(
                sa.text(
                    "DELETE FROM role_permissions "
                    "WHERE role_id=:role_id AND permission_id=:permission_id"
                ).bindparams(role_id=role_id, permission_id=permission_id)
            )
    op.execute("DELETE FROM permissions WHERE id LIKE 'perm-inventory-%'")
