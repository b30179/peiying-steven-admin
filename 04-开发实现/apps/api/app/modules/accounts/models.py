from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, MetaData, String, Table, Text, UniqueConstraint, func, true

metadata = MetaData()

users = Table(
    "users",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("username", String(100), nullable=False),
    Column("display_name", String(200), nullable=False),
    Column("email", String(320), nullable=True),
    Column("password_hash", Text(), nullable=False),
    Column("status", String(32), nullable=False, server_default="active"),
    Column("failed_login_count", Integer(), nullable=False, server_default="0"),
    Column("locked_until", DateTime(timezone=True), nullable=True),
    Column("last_login_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("status IN ('active','disabled','locked')", name="ck_users_status"),
    UniqueConstraint("username", name="uq_users_username"),
    UniqueConstraint("email", name="uq_users_email"),
    Index("ix_users_status", "status"),
)
Index("uq_users_username_lower", func.lower(users.c.username), unique=True)
roles = Table(
    "roles",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("code", String(100), nullable=False),
    Column("name", String(200), nullable=False),
    Column("status", String(32), nullable=False, server_default="active"),
    CheckConstraint("status IN ('active','disabled')", name="ck_roles_status"),
    UniqueConstraint("code", name="uq_roles_code"),
)
permissions = Table(
    "permissions",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("code", String(150), nullable=False),
    Column("name", String(200), nullable=False),
    Column("module", String(100), nullable=False),
    UniqueConstraint("code", name="uq_permissions_code"),
    Index("ix_permissions_module", "module"),
)
user_roles = Table(
    "user_roles",
    metadata,
    Column("user_id", String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", String(36), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("assigned_by", String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    Column("assigned_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),
    Index("ix_user_roles_role_id", "role_id"),
)
role_permissions = Table(
    "role_permissions",
    metadata,
    Column("role_id", String(36), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", String(36), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
    UniqueConstraint("role_id", "permission_id", name="uq_role_permissions_role_permission"),
    Index("ix_role_permissions_permission_id", "permission_id"),
)
auth_sessions = Table(
    "auth_sessions",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("user_id", String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("token_hash", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("last_seen_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("idle_expires_at", DateTime(timezone=True), nullable=False),
    Column("absolute_expires_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
    Column("revoke_reason", String(200), nullable=True),
    Column("ip_hash", String(64), nullable=True),
    Column("user_agent_hash", String(64), nullable=True),
    Column("is_active", Boolean(), nullable=False, server_default=true()),
    CheckConstraint("absolute_expires_at > created_at", name="ck_auth_sessions_absolute_expiry"),
    CheckConstraint("idle_expires_at <= absolute_expires_at", name="ck_auth_sessions_idle_expiry"),
    UniqueConstraint("token_hash", name="uq_auth_sessions_token_hash"),
    Index("ix_auth_sessions_user_active", "user_id", "is_active"),
    Index("ix_auth_sessions_expiry", "idle_expires_at", "absolute_expires_at"),
)
