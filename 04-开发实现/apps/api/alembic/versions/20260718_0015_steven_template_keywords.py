"""Add S1 template recommendation keywords.

Revision ID: 20260718_0015
Revises: 20260717_0014
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260718_0015"
down_revision = "20260717_0014"
branch_labels = None
depends_on = None


TEMPLATE_KEYWORDS = {
    "DEMO-SERVICE-INVITATION": [
        "采购",
        "採購",
        "procurement",
        "標書",
        "标书",
        "服務",
        "服务",
        "invitation",
    ],
    "DEMO-QUOTATION-REQUEST": [
        "报价",
        "報價",
        "quotation",
        "詢價",
        "询价",
        "比價",
        "比价",
        "request",
    ],
    "DEMO-SERVICE-PROPOSAL-REQUEST": [
        "方案",
        "proposal",
        "征集",
        "徵集",
        "服務建議",
        "服务建议",
        "計劃",
        "计划",
    ],
}


def upgrade() -> None:
    op.add_column(
        "steven_templates",
        sa.Column(
            "keywords",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    connection = op.get_bind()
    for template_code, keywords in TEMPLATE_KEYWORDS.items():
        connection.execute(
            sa.text(
                """
                UPDATE steven_templates
                SET keywords = CAST(:keywords AS jsonb), updated_at = now()
                WHERE code = :template_code
                """
            ),
            {"template_code": template_code, "keywords": json.dumps(keywords, ensure_ascii=False)},
        )


def downgrade() -> None:
    op.drop_column("steven_templates", "keywords")
