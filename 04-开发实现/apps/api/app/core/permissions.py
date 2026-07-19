from __future__ import annotations

from types import MappingProxyType

DASHBOARD_READ = "steven:dashboard:read"
QUOTES_READ = "steven:quotes:read"
QUOTES_WRITE = "steven:quotes:write"
QUOTES_IMPORT = "steven:quotes:import"
QUOTES_RECOMMEND = "steven:quotes:recommend"
QUOTES_SUBMIT = "steven:quotes:submit"
QUOTES_APPROVE = "steven:quotes:approve"
QUOTES_EXPORT = "steven:quotes:export"
QUOTES_AUDIT_SCOPED = "steven:quotes:audit:read_scoped"
TENDERS_READ = "steven:tenders:read"
TENDERS_WRITE = "steven:tenders:write"
TENDERS_SUBMIT = "steven:tenders:submit"
TENDERS_APPROVE = "steven:tenders:approve"
TENDERS_EXPORT = "steven:tenders:export"
TENDERS_AUDIT_SCOPED = "steven:tenders:audit:read_scoped"
INVENTORY_READ = "steven:inventory:read"
INVENTORY_WRITE = "steven:inventory:write"
INVENTORY_COUNT = "steven:inventory:count"
INVENTORY_SUBMIT = "steven:inventory:submit"
INVENTORY_APPROVE = "steven:inventory:approve"
INVENTORY_EXPORT = "steven:inventory:export"
INVENTORY_AUDIT_SCOPED = "steven:inventory:audit:read_scoped"
AUDIT_READ_ALL = "audit:logs:read_all"
ACCOUNTS_MANAGE = "accounts:manage"
ROLES_MANAGE = "roles:manage"
SESSIONS_MANAGE = "sessions:manage"
NOTIFICATIONS_READ_OWN = "notifications:read_own"
NOTIFICATIONS_UPDATE_OWN = "notifications:update_own"
PROFILE_READ_OWN = "profile:read_own"
PROFILE_UPDATE_OWN = "profile:update_own"
PASSWORD_CHANGE_OWN = "password:change_own"
STEVEN_HISTORY_READ_SCOPED = "steven:history:read_scoped"
TENDERS_PROOFREAD = "steven:tenders:proofread"

OPERATOR_PERMISSIONS = frozenset({
    DASHBOARD_READ,
    QUOTES_READ,
    QUOTES_WRITE,
    QUOTES_IMPORT,
    QUOTES_RECOMMEND,
    QUOTES_SUBMIT,
    QUOTES_EXPORT,
    QUOTES_AUDIT_SCOPED,
    TENDERS_READ,
    TENDERS_WRITE,
    TENDERS_SUBMIT,
    TENDERS_EXPORT,
    TENDERS_AUDIT_SCOPED,
    INVENTORY_READ,
    INVENTORY_WRITE,
    INVENTORY_COUNT,
    INVENTORY_SUBMIT,
    INVENTORY_EXPORT,
    INVENTORY_AUDIT_SCOPED,
    NOTIFICATIONS_READ_OWN,
    NOTIFICATIONS_UPDATE_OWN,
    PROFILE_READ_OWN,
    PROFILE_UPDATE_OWN,
    PASSWORD_CHANGE_OWN,
    STEVEN_HISTORY_READ_SCOPED,
    TENDERS_PROOFREAD,
})
APPROVER_PERMISSIONS = frozenset({
    DASHBOARD_READ,
    QUOTES_READ,
    QUOTES_APPROVE,
    QUOTES_AUDIT_SCOPED,
    TENDERS_READ,
    TENDERS_APPROVE,
    TENDERS_AUDIT_SCOPED,
    INVENTORY_READ,
    INVENTORY_APPROVE,
    INVENTORY_AUDIT_SCOPED,
    NOTIFICATIONS_READ_OWN,
    NOTIFICATIONS_UPDATE_OWN,
    PROFILE_READ_OWN,
    PROFILE_UPDATE_OWN,
    PASSWORD_CHANGE_OWN,
    STEVEN_HISTORY_READ_SCOPED,
    TENDERS_PROOFREAD,
})
ADMIN_PERMISSIONS = frozenset({
    DASHBOARD_READ,
    AUDIT_READ_ALL,
    ACCOUNTS_MANAGE,
    ROLES_MANAGE,
    SESSIONS_MANAGE,
    NOTIFICATIONS_READ_OWN,
    NOTIFICATIONS_UPDATE_OWN,
    PROFILE_READ_OWN,
    PROFILE_UPDATE_OWN,
    PASSWORD_CHANGE_OWN,
    STEVEN_HISTORY_READ_SCOPED,
})

ROLE_PERMISSIONS = MappingProxyType({
    "operator": OPERATOR_PERMISSIONS,
    "approver": APPROVER_PERMISSIONS,
    "admin": ADMIN_PERMISSIONS,
})
ALL_PERMISSIONS = frozenset().union(*ROLE_PERMISSIONS.values())
