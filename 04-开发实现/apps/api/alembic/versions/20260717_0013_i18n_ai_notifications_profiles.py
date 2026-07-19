"""Add locale preferences, notifications and S1 proofreading candidates."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260717_0013"
down_revision = "20260717_0012"
branch_labels = None
depends_on = None

PERMISSIONS = (
    ("perm-notifications-read-own", "notifications:read_own", "讀取個人通知", "platform"),
    ("perm-notifications-update-own", "notifications:update_own", "更新個人通知", "platform"),
    ("perm-profile-read-own", "profile:read_own", "讀取個人設定", "platform"),
    ("perm-profile-update-own", "profile:update_own", "更新個人設定", "platform"),
    ("perm-password-change-own", "password:change_own", "修改個人密碼", "platform"),
    ("perm-steven-history-read-scoped", "steven:history:read_scoped", "讀取 Steven 範圍歷史", "steven"),
    ("perm-tender-proofread", "steven:tenders:proofread", "執行及覆核 S1 AI 校對", "steven"),
)


def upgrade() -> None:
    op.create_table(
        "user_preferences",
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("locale", sa.String(length=10), nullable=False, server_default="zh-TW"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("locale IN ('zh-TW','zh-CN')", name="ck_user_preferences_locale"),
    )
    op.create_table(
        "user_notifications",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("recipient_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_audit_event_id", sa.String(length=36), sa.ForeignKey("platform_audit_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("module", sa.String(length=20), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("object_type", sa.String(length=100), nullable=False),
        sa.Column("object_id", sa.String(length=100), nullable=False),
        sa.Column("target_path", sa.String(length=500), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("request_id", sa.String(length=100), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("recipient_user_id", "source_audit_event_id", name="uq_user_notifications_recipient_audit"),
    )
    op.create_index("ix_user_notifications_recipient_unread", "user_notifications", ["recipient_user_id", "read_at", "created_at"])
    op.create_index("ix_user_notifications_object", "user_notifications", ["module", "object_type", "object_id", "created_at"])
    op.create_table(
        "steven_tender_review_candidates",
        sa.Column("candidate_id", sa.String(length=36), sa.ForeignKey("review_candidates.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("tender_job_id", sa.String(length=36), sa.ForeignKey("steven_tender_jobs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("draft_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("draft_sha256 ~ '^[a-f0-9]{64}$'", name="ck_steven_tender_review_candidates_sha256"),
    )
    op.create_index("ix_steven_tender_review_candidates_job", "steven_tender_review_candidates", ["tender_job_id", "created_at"])
    op.drop_constraint("ck_steven_tender_candidate_kind", "steven_tender_candidate_links", type_="check")
    op.create_check_constraint("ck_steven_tender_candidate_kind", "steven_tender_candidate_links", "candidate_kind IN ('tender_source_extraction','clause_draft','tender_proofreading')")

    permissions = sa.table("permissions", sa.column("id", sa.String()), sa.column("code", sa.String()), sa.column("name", sa.String()), sa.column("module", sa.String()))
    op.bulk_insert(permissions, [{"id": row[0], "code": row[1], "name": row[2], "module": row[3]} for row in PERMISSIONS])
    common = ("perm-notifications-read-own", "perm-notifications-update-own", "perm-profile-read-own", "perm-profile-update-own", "perm-password-change-own", "perm-steven-history-read-scoped")
    for role_id in ("role-steven", "role-approver", "role-admin"):
        for permission_id in common:
            op.execute(sa.text("INSERT INTO role_permissions (role_id,permission_id) VALUES (:r,:p) ON CONFLICT DO NOTHING").bindparams(r=role_id, p=permission_id))
    for role_id in ("role-steven", "role-approver"):
        op.execute(sa.text("INSERT INTO role_permissions (role_id,permission_id) VALUES (:r,'perm-tender-proofread') ON CONFLICT DO NOTHING").bindparams(r=role_id))
    op.execute(
        """
        CREATE OR REPLACE FUNCTION steven_create_notification_from_audit()
        RETURNS trigger AS $$
        DECLARE
            recipient record;
            submitted_user_id text;
            permission_code text;
            target_module text;
            target_path text;
        BEGIN
            IF NEW.outcome <> 'success' OR NEW.action NOT IN (
                'tender.submit','tender.approve','tender.return',
                'quote.submit','quote.approve','quote.reject',
                'inventory.count.submit','inventory.count.approve','inventory.count.return'
            ) THEN RETURN NEW; END IF;

            IF NEW.action LIKE 'tender.%' THEN
                target_module := 's1'; target_path := '/dashboard/steven/tenders/' || NEW.object_id;
            ELSIF NEW.action LIKE 'quote.%' THEN
                target_module := 's2'; target_path := '/dashboard/steven/quotes/' || NEW.object_id;
            ELSE
                target_module := 's3'; target_path := '/dashboard/steven/inventory/' || NEW.object_id;
            END IF;

            IF NEW.action IN ('tender.submit','quote.submit','inventory.count.submit') THEN
                permission_code := CASE
                    WHEN NEW.action = 'tender.submit' THEN 'steven:tenders:approve'
                    WHEN NEW.action = 'quote.submit' THEN 'steven:quotes:approve'
                    ELSE 'steven:inventory:approve' END;
                FOR recipient IN
                    SELECT DISTINCT u.id FROM users u
                    JOIN user_roles ur ON ur.user_id=u.id
                    JOIN role_permissions rp ON rp.role_id=ur.role_id
                    JOIN permissions p ON p.id=rp.permission_id
                    WHERE u.status='active' AND p.code=permission_code AND u.id IS DISTINCT FROM NEW.actor_user_id
                LOOP
                    INSERT INTO user_notifications (id,recipient_user_id,actor_user_id,source_audit_event_id,module,event_type,object_type,object_id,target_path,payload_json,request_id,created_at)
                    VALUES (md5(random()::text||clock_timestamp()::text||NEW.id||recipient.id),recipient.id,NEW.actor_user_id,NEW.id,target_module,NEW.action,NEW.object_type,NEW.object_id,target_path,'{}'::jsonb,NEW.request_id,NEW.occurred_at)
                    ON CONFLICT DO NOTHING;
                END LOOP;
            ELSE
                IF NEW.action LIKE 'tender.%' THEN SELECT submitted_by INTO submitted_user_id FROM steven_tender_jobs WHERE id=NEW.object_id;
                ELSIF NEW.action LIKE 'quote.%' THEN SELECT submitted_by INTO submitted_user_id FROM steven_quote_jobs WHERE id=NEW.object_id;
                ELSE SELECT submitted_by INTO submitted_user_id FROM steven_inventory_counts WHERE id=NEW.object_id; END IF;
                IF submitted_user_id IS NOT NULL AND submitted_user_id IS DISTINCT FROM NEW.actor_user_id THEN
                    INSERT INTO user_notifications (id,recipient_user_id,actor_user_id,source_audit_event_id,module,event_type,object_type,object_id,target_path,payload_json,request_id,created_at)
                    VALUES (md5(random()::text||clock_timestamp()::text||NEW.id||submitted_user_id),submitted_user_id,NEW.actor_user_id,NEW.id,target_module,NEW.action,NEW.object_type,NEW.object_id,target_path,'{}'::jsonb,NEW.request_id,NEW.occurred_at)
                    ON CONFLICT DO NOTHING;
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_steven_notification_from_audit
        AFTER INSERT ON platform_audit_events
        FOR EACH ROW EXECUTE FUNCTION steven_create_notification_from_audit();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_steven_notification_from_audit ON platform_audit_events")
    op.execute("DROP FUNCTION IF EXISTS steven_create_notification_from_audit()")
    for role_id in ("role-steven", "role-approver", "role-admin"):
        for permission_id, *_ in PERMISSIONS:
            op.execute(sa.text("DELETE FROM role_permissions WHERE role_id=:r AND permission_id=:p").bindparams(r=role_id, p=permission_id))
    op.execute("DELETE FROM permissions WHERE id LIKE 'perm-notifications-%' OR id IN ('perm-profile-read-own','perm-profile-update-own','perm-password-change-own','perm-steven-history-read-scoped','perm-tender-proofread')")
    op.drop_constraint("ck_steven_tender_candidate_kind", "steven_tender_candidate_links", type_="check")
    op.create_check_constraint("ck_steven_tender_candidate_kind", "steven_tender_candidate_links", "candidate_kind IN ('tender_source_extraction','clause_draft')")
    op.drop_index("ix_steven_tender_review_candidates_job", table_name="steven_tender_review_candidates")
    op.drop_table("steven_tender_review_candidates")
    op.drop_index("ix_user_notifications_object", table_name="user_notifications")
    op.drop_index("ix_user_notifications_recipient_unread", table_name="user_notifications")
    op.drop_table("user_notifications")
    op.drop_table("user_preferences")