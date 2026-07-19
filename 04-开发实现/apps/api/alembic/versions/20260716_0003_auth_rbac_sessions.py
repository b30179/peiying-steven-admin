"""Add P0-A local accounts, permission RBAC and hashed server sessions."""

from alembic import op
import sqlalchemy as sa

revision = "20260716_0003"
down_revision = "20260716_0002"
branch_labels = None
depends_on = None

ROLE_ROWS = [
    {"id": "role-steven", "code": "steven", "name": "Steven", "status": "active"},
    {"id": "role-approver", "code": "approver", "name": "审批人", "status": "active"},
    {"id": "role-admin", "code": "admin", "name": "管理员", "status": "active"},
]
PERMISSION_ROWS = [
    ("perm-dashboard-read", "steven:dashboard:read", "读取 Steven Dashboard", "steven"),
    ("perm-quotes-read", "steven:quotes:read", "读取采购比价", "steven"),
    ("perm-quotes-write", "steven:quotes:write", "写入采购比价", "steven"),
    ("perm-quotes-import", "steven:quotes:import", "导入采购比价", "steven"),
    ("perm-quotes-recommend", "steven:quotes:recommend", "填写人工推荐", "steven"),
    ("perm-quotes-submit", "steven:quotes:submit", "提交采购审批", "steven"),
    ("perm-quotes-approve", "steven:quotes:approve", "批准或退回采购审批", "steven"),
    ("perm-quotes-export", "steven:quotes:export", "导出已批准采购比价", "steven"),
    ("perm-quotes-audit-scoped", "steven:quotes:audit:read_scoped", "读取事项级审计", "steven"),
    ("perm-audit-read-all", "audit:logs:read_all", "读取平台全量审计", "platform"),
    ("perm-accounts-manage", "accounts:manage", "管理账户", "platform"),
    ("perm-roles-manage", "roles:manage", "管理角色", "platform"),
    ("perm-sessions-manage", "sessions:manage", "管理会话", "platform"),
]
ROLE_PERMISSION_ROWS = {
    "role-steven": ["perm-dashboard-read", "perm-quotes-read", "perm-quotes-write", "perm-quotes-import", "perm-quotes-recommend", "perm-quotes-submit", "perm-quotes-export", "perm-quotes-audit-scoped"],
    "role-approver": ["perm-quotes-read", "perm-quotes-approve", "perm-quotes-audit-scoped"],
    "role-admin": ["perm-audit-read-all", "perm-accounts-manage", "perm-roles-manage", "perm-sessions-manage"],
}


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('active','disabled','locked')", name="ck_users_status"),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_status", "users", ["status"])
    op.create_table(
        "roles",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.CheckConstraint("status IN ('active','disabled')", name="ck_roles_status"),
        sa.UniqueConstraint("code", name="uq_roles_code"),
    )
    op.create_table(
        "permissions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(length=150), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("module", sa.String(length=100), nullable=False),
        sa.UniqueConstraint("code", name="uq_permissions_code"),
    )
    op.create_index("ix_permissions_module", "permissions", ["module"])
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_id", sa.String(length=36), sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assigned_by", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("user_id", "role_id", name="pk_user_roles"),
        sa.UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),
    )
    op.create_index("ix_user_roles_role_id", "user_roles", ["role_id"])
    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.String(length=36), sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("permission_id", sa.String(length=36), sa.ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False),
        sa.PrimaryKeyConstraint("role_id", "permission_id", name="pk_role_permissions"),
        sa.UniqueConstraint("role_id", "permission_id", name="uq_role_permissions_role_permission"),
    )
    op.create_index("ix_role_permissions_permission_id", "role_permissions", ["permission_id"])
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.String(length=200), nullable=True),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column("user_agent_hash", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.CheckConstraint("absolute_expires_at > created_at", name="ck_auth_sessions_absolute_expiry"),
        sa.CheckConstraint("idle_expires_at <= absolute_expires_at", name="ck_auth_sessions_idle_expiry"),
        sa.UniqueConstraint("token_hash", name="uq_auth_sessions_token_hash"),
    )
    op.create_index("ix_auth_sessions_user_active", "auth_sessions", ["user_id", "is_active"])
    op.create_index("ix_auth_sessions_expiry", "auth_sessions", ["idle_expires_at", "absolute_expires_at"])

    role_table = sa.table("roles", sa.column("id", sa.String), sa.column("code", sa.String), sa.column("name", sa.String), sa.column("status", sa.String))
    permission_table = sa.table("permissions", sa.column("id", sa.String), sa.column("code", sa.String), sa.column("name", sa.String), sa.column("module", sa.String))
    role_permission_table = sa.table("role_permissions", sa.column("role_id", sa.String), sa.column("permission_id", sa.String))
    op.bulk_insert(role_table, ROLE_ROWS)
    op.bulk_insert(permission_table, [{"id": item[0], "code": item[1], "name": item[2], "module": item[3]} for item in PERMISSION_ROWS])
    op.bulk_insert(role_permission_table, [{"role_id": role_id, "permission_id": permission_id} for role_id, permission_ids in ROLE_PERMISSION_ROWS.items() for permission_id in permission_ids])


def downgrade() -> None:
    op.drop_index("ix_auth_sessions_expiry", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_user_active", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index("ix_role_permissions_permission_id", table_name="role_permissions")
    op.drop_table("role_permissions")
    op.drop_index("ix_user_roles_role_id", table_name="user_roles")
    op.drop_table("user_roles")
    op.drop_index("ix_permissions_module", table_name="permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_index("ix_users_status", table_name="users")
    op.drop_table("users")
