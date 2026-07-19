"""Create Phase 1 quote hierarchy and supplier-item uniqueness constraint."""

from alembic import op
import sqlalchemy as sa

revision = "20260716_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "steven_quote_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
    )
    op.create_table(
        "steven_quote_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("quote_job_id", sa.String(length=36), sa.ForeignKey("steven_quote_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 2), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_steven_quote_items_quantity_positive"),
    )
    op.create_table(
        "steven_quote_suppliers",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("quote_job_id", sa.String(length=36), sa.ForeignKey("steven_quote_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("supplier_name", sa.String(length=200), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("freight", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("tax", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.CheckConstraint("freight >= 0", name="ck_steven_quote_suppliers_freight_nonnegative"),
        sa.CheckConstraint("tax >= 0", name="ck_steven_quote_suppliers_tax_nonnegative"),
    )
    op.create_table(
        "steven_quote_offer_lines",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("quote_supplier_id", sa.String(length=36), sa.ForeignKey("steven_quote_suppliers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quote_item_id", sa.String(length=36), sa.ForeignKey("steven_quote_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("unit_price", sa.Numeric(14, 2), nullable=False),
        sa.CheckConstraint("unit_price >= 0", name="ck_steven_quote_offer_lines_unit_price_nonnegative"),
        sa.UniqueConstraint("quote_supplier_id", "quote_item_id", name="uq_steven_quote_offer_lines_supplier_item"),
    )


def downgrade() -> None:
    op.drop_table("steven_quote_offer_lines")
    op.drop_table("steven_quote_suppliers")
    op.drop_table("steven_quote_items")
    op.drop_table("steven_quote_jobs")