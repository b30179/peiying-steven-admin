"""Add controlled S3 inventory Excel import preflight and confirmation."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260717_0011"
down_revision = "20260717_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "steven_inventory_import_batches",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("valid_count", sa.Integer(), nullable=False),
        sa.Column("invalid_count", sa.Integer(), nullable=False),
        sa.Column("issues", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("confirmed_by", sa.String(length=36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("request_id", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('preflight_ready','confirmed','rejected','failed')",
            name="ck_steven_inventory_import_batches_status",
        ),
        sa.CheckConstraint(
            "row_count >= 0 AND valid_count >= 0 AND invalid_count >= 0",
            name="ck_steven_inventory_import_batches_counts",
        ),
        sa.CheckConstraint(
            "row_count = valid_count + invalid_count",
            name="ck_steven_inventory_import_batches_count_total",
        ),
    )
    op.create_index(
        "ix_steven_inventory_import_batches_status_created",
        "steven_inventory_import_batches",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_steven_inventory_import_batches_request_id",
        "steven_inventory_import_batches",
        ["request_id", "created_at"],
    )

    op.create_table(
        "steven_inventory_import_rows",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "batch_id",
            sa.String(length=36),
            sa.ForeignKey("steven_inventory_import_batches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("raw_values", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("values", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("normalized_sku", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("errors", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column(
            "imported_item_id",
            sa.String(length=36),
            sa.ForeignKey("steven_inventory_items.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("row_number >= 2", name="ck_steven_inventory_import_rows_number"),
        sa.CheckConstraint(
            "status IN ('valid','invalid','confirmed')",
            name="ck_steven_inventory_import_rows_status",
        ),
        sa.UniqueConstraint("batch_id", "row_number", name="uq_steven_inventory_import_rows_batch_row"),
    )
    op.create_index(
        "ix_steven_inventory_import_rows_batch_status",
        "steven_inventory_import_rows",
        ["batch_id", "status", "row_number"],
    )
    op.create_index(
        "ix_steven_inventory_import_rows_normalized_sku",
        "steven_inventory_import_rows",
        ["normalized_sku"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_steven_inventory_import_rows_normalized_sku",
        table_name="steven_inventory_import_rows",
    )
    op.drop_index(
        "ix_steven_inventory_import_rows_batch_status",
        table_name="steven_inventory_import_rows",
    )
    op.drop_table("steven_inventory_import_rows")
    op.drop_index(
        "ix_steven_inventory_import_batches_request_id",
        table_name="steven_inventory_import_batches",
    )
    op.drop_index(
        "ix_steven_inventory_import_batches_status_created",
        table_name="steven_inventory_import_batches",
    )
    op.drop_table("steven_inventory_import_batches")
