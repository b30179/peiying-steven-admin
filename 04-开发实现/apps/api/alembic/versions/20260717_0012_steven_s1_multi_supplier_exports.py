"""Add supplier-isolated batch Word export metadata for S1."""

from alembic import op
import sqlalchemy as sa


revision = "20260717_0012"
down_revision = "20260717_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("steven_tender_versions", sa.Column("export_batch_id", sa.String(length=36), nullable=True))
    op.add_column("steven_tender_versions", sa.Column("supplier_id", sa.String(length=36), nullable=True))
    op.add_column("steven_tender_versions", sa.Column("supplier_name_snapshot", sa.String(length=250), nullable=True))
    op.create_foreign_key(
        "fk_steven_tender_versions_supplier",
        "steven_tender_versions",
        "steven_tender_suppliers",
        ["supplier_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_steven_tender_versions_batch_supplier_metadata",
        "steven_tender_versions",
        "(export_batch_id IS NULL AND supplier_id IS NULL AND supplier_name_snapshot IS NULL) OR "
        "(export_batch_id IS NOT NULL AND btrim(export_batch_id) <> '' AND supplier_id IS NOT NULL "
        "AND supplier_name_snapshot IS NOT NULL AND btrim(supplier_name_snapshot) <> '')",
    )
    op.create_index(
        "ix_steven_tender_versions_export_batch",
        "steven_tender_versions",
        ["export_batch_id", "version_number"],
    )
    op.create_index(
        "ix_steven_tender_versions_supplier",
        "steven_tender_versions",
        ["supplier_id", "version_number"],
    )


def downgrade() -> None:
    op.drop_index("ix_steven_tender_versions_supplier", table_name="steven_tender_versions")
    op.drop_index("ix_steven_tender_versions_export_batch", table_name="steven_tender_versions")
    op.drop_constraint(
        "ck_steven_tender_versions_batch_supplier_metadata",
        "steven_tender_versions",
        type_="check",
    )
    op.drop_constraint(
        "fk_steven_tender_versions_supplier",
        "steven_tender_versions",
        type_="foreignkey",
    )
    op.drop_column("steven_tender_versions", "supplier_name_snapshot")
    op.drop_column("steven_tender_versions", "supplier_id")
    op.drop_column("steven_tender_versions", "export_batch_id")
