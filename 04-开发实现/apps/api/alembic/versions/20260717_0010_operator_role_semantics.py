"""Rename the Steven user role to the reusable operator role."""

from alembic import op


revision = "20260717_0010"
down_revision = "20260717_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE
            current_code text;
            conflicting_role_id text;
        BEGIN
            SELECT code INTO current_code
              FROM roles
             WHERE id = 'role-steven'
             FOR UPDATE;

            IF current_code IS NULL THEN
                RAISE EXCEPTION 'role-steven is missing; operator role migration cannot continue';
            END IF;

            SELECT id INTO conflicting_role_id
              FROM roles
             WHERE code = 'operator'
               AND id <> 'role-steven'
             LIMIT 1;

            IF conflicting_role_id IS NOT NULL THEN
                RAISE EXCEPTION 'operator role code is already used by %', conflicting_role_id;
            END IF;

            IF current_code NOT IN ('steven', 'operator') THEN
                RAISE EXCEPTION 'role-steven has unexpected code: %', current_code;
            END IF;

            UPDATE roles
               SET code = 'operator',
                   name = '业务操作员'
             WHERE id = 'role-steven';

            INSERT INTO role_permissions (role_id, permission_id)
            VALUES
                ('role-approver', 'perm-dashboard-read'),
                ('role-admin', 'perm-dashboard-read')
            ON CONFLICT DO NOTHING;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE
            current_code text;
            conflicting_role_id text;
        BEGIN
            DELETE FROM role_permissions
             WHERE permission_id = 'perm-dashboard-read'
               AND role_id IN ('role-approver', 'role-admin');

            SELECT code INTO current_code
              FROM roles
             WHERE id = 'role-steven'
             FOR UPDATE;

            IF current_code IS NULL THEN
                RAISE EXCEPTION 'role-steven is missing; role downgrade cannot continue';
            END IF;

            SELECT id INTO conflicting_role_id
              FROM roles
             WHERE code = 'steven'
               AND id <> 'role-steven'
             LIMIT 1;

            IF conflicting_role_id IS NOT NULL THEN
                RAISE EXCEPTION 'steven role code is already used by %', conflicting_role_id;
            END IF;

            IF current_code NOT IN ('operator', 'steven') THEN
                RAISE EXCEPTION 'role-steven has unexpected code: %', current_code;
            END IF;

            UPDATE roles
               SET code = 'steven',
                   name = 'Steven'
             WHERE id = 'role-steven';
        END $$;
        """
    )
