"""Fix S2 approval notification submitter lookup.

Revision ID: 20260717_0014
Revises: 20260717_0013
"""

from alembic import op


revision = "20260717_0014"
down_revision = "20260717_0013"
branch_labels = None
depends_on = None


def _function_sql(quote_submitter_lookup: str) -> str:
    return f"""
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
                INSERT INTO user_notifications (
                    id,recipient_user_id,actor_user_id,source_audit_event_id,module,event_type,
                    object_type,object_id,target_path,payload_json,request_id,created_at
                ) VALUES (
                    md5(random()::text||clock_timestamp()::text||NEW.id||recipient.id),recipient.id,
                    NEW.actor_user_id,NEW.id,target_module,NEW.action,NEW.object_type,NEW.object_id,
                    target_path,'{{}}'::jsonb,NEW.request_id,NEW.occurred_at
                ) ON CONFLICT DO NOTHING;
            END LOOP;
        ELSE
            IF NEW.action LIKE 'tender.%' THEN
                SELECT submitted_by INTO submitted_user_id
                FROM steven_tender_jobs WHERE id=NEW.object_id;
            ELSIF NEW.action LIKE 'quote.%' THEN
                {quote_submitter_lookup}
            ELSE
                SELECT submitted_by INTO submitted_user_id
                FROM steven_inventory_counts WHERE id=NEW.object_id;
            END IF;
            IF submitted_user_id IS NOT NULL AND submitted_user_id IS DISTINCT FROM NEW.actor_user_id THEN
                INSERT INTO user_notifications (
                    id,recipient_user_id,actor_user_id,source_audit_event_id,module,event_type,
                    object_type,object_id,target_path,payload_json,request_id,created_at
                ) VALUES (
                    md5(random()::text||clock_timestamp()::text||NEW.id||submitted_user_id),submitted_user_id,
                    NEW.actor_user_id,NEW.id,target_module,NEW.action,NEW.object_type,NEW.object_id,
                    target_path,'{{}}'::jsonb,NEW.request_id,NEW.occurred_at
                ) ON CONFLICT DO NOTHING;
            END IF;
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """


S2_AUDIT_LOOKUP = """
SELECT actor_user_id INTO submitted_user_id
FROM steven_quote_audit_events
WHERE object_id=NEW.object_id AND action='quote.submit'
ORDER BY occurred_at DESC,id DESC LIMIT 1;
""".strip()

LEGACY_QUOTE_JOB_LOOKUP = """
SELECT submitted_by INTO submitted_user_id
FROM steven_quote_jobs WHERE id=NEW.object_id;
""".strip()


def upgrade() -> None:
    op.execute(_function_sql(S2_AUDIT_LOOKUP))


def downgrade() -> None:
    op.execute(_function_sql(LEGACY_QUOTE_JOB_LOOKUP))
