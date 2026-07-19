from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from threading import RLock
from typing import Protocol
from uuid import uuid4

from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from app.core.audit import PlatformAuditRepository
from app.core.audit_context import current_request_id
from app.core.passwords import hash_password, verify_password
from app.core.permissions import ROLE_PERMISSIONS


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class AccountIdentity:
    user_id: str
    username: str
    display_name: str
    roles: frozenset[str]
    permissions: frozenset[str]


@dataclass(frozen=True)
class AuthenticationResult:
    outcome: str
    identity: AccountIdentity | None = None


@dataclass
class UserRecord:
    id: str
    username: str
    display_name: str
    password_hash: str
    roles: frozenset[str]
    status: str = "active"
    failed_login_count: int = 0
    locked_until: datetime | None = None
    last_login_at: datetime | None = None

    @property
    def permissions(self) -> frozenset[str]:
        return frozenset().union(*(ROLE_PERMISSIONS.get(role, frozenset()) for role in self.roles))


@dataclass
class SessionRecord:
    id: str
    user_id: str
    token_hash: str
    created_at: datetime
    last_seen_at: datetime
    idle_expires_at: datetime
    absolute_expires_at: datetime
    revoked_at: datetime | None = None
    revoke_reason: str | None = None


class AuthRepository(Protocol):
    def authenticate(self, username: str, password: str, max_failures: int, lock_minutes: int) -> AuthenticationResult: ...
    def create_session(self, user_id: str, token_hash: str, idle_minutes: int, absolute_hours: int) -> SessionRecord: ...
    def resolve_session(self, token_hash: str, idle_minutes: int) -> tuple[AccountIdentity, SessionRecord] | None: ...
    def revoke_session(self, session_id: str, reason: str) -> bool: ...
    def list_users(self) -> list[dict]: ...
    def list_roles(self) -> list[dict]: ...
    def list_sessions(self) -> list[dict]: ...
    def create_user(self, username: str, display_name: str, password: str, roles: set[str], actor_id: str) -> dict: ...
    def set_user_roles(self, user_id: str, roles: set[str], actor_id: str) -> dict: ...
    def disable_user(self, user_id: str, actor_id: str) -> bool: ...
    def bootstrap_admin(self, username: str, display_name: str, password: str) -> dict: ...
    def reset_demo_passwords(self, usernames: list[str], password: str) -> list[dict]: ...
    def sync_demo_accounts(self, password: str) -> dict: ...
    def list_security_events(self) -> list[dict]: ...
    def record_security_event(self, event_type: str, outcome: str, actor_user_id: str | None, subject_user_id: str | None, details: dict) -> None: ...


class InMemoryAuthRepository:
    def __init__(self) -> None:
        self._lock = RLock()
        self._users: dict[str, UserRecord] = {}
        self._usernames: dict[str, str] = {}
        self._sessions: dict[str, SessionRecord] = {}
        self._sessions_by_hash: dict[str, str] = {}
        self._security_events: list[dict] = []
        self._platform_audit: PlatformAuditRepository | None = None

    def set_platform_audit_repository(self, repository: PlatformAuditRepository) -> None:
        self._platform_audit = repository

    def add_user(self, username: str, password: str, roles: set[str], display_name: str | None = None, user_id: str | None = None) -> UserRecord:
        record = UserRecord(user_id or str(uuid4()), username, display_name or username, hash_password(password), frozenset(roles))
        with self._lock:
            self._users[record.id] = record
            self._usernames[username.casefold()] = record.id
        return record

    def authenticate(self, username: str, password: str, max_failures: int, lock_minutes: int) -> AuthenticationResult:
        with self._lock:
            user_id = self._usernames.get(username.casefold())
            record = self._users.get(user_id) if user_id else None
            now = utc_now()
            if record is None:
                self._record_security_event("auth.login_failed", "rejected", None, None, {"reason": "invalid_credentials", "username": username.casefold()})
                return AuthenticationResult("invalid_credentials")
            if record.status != "active":
                self._record_security_event("auth.login_failed", "rejected", None, record.id, {"reason": "account_disabled"})
                return AuthenticationResult("disabled")
            if record.locked_until and now < record.locked_until:
                self._record_security_event("auth.login_failed", "rejected", None, record.id, {"reason": "account_locked"})
                return AuthenticationResult("locked")
            if not verify_password(password, record.password_hash):
                record.failed_login_count += 1
                if record.failed_login_count >= max_failures:
                    record.locked_until = now + timedelta(minutes=lock_minutes)
                self._record_security_event(
                    "auth.login_failed",
                    "rejected",
                    None,
                    record.id,
                    {"reason": "invalid_credentials", "failed_login_count": record.failed_login_count, "locked": record.locked_until is not None},
                )
                return AuthenticationResult("locked" if record.locked_until else "invalid_credentials")
            record.failed_login_count = 0
            record.locked_until = None
            record.last_login_at = now
            self._record_security_event("auth.login_succeeded", "success", record.id, record.id, {})
            return AuthenticationResult("success", self._identity(record))

    def create_session(self, user_id: str, token_hash: str, idle_minutes: int, absolute_hours: int) -> SessionRecord:
        now = utc_now()
        record = SessionRecord(str(uuid4()), user_id, token_hash, now, now, now + timedelta(minutes=idle_minutes), now + timedelta(hours=absolute_hours))
        with self._lock:
            self._sessions[record.id] = record
            self._sessions_by_hash[token_hash] = record.id
        return record

    def resolve_session(self, token_hash: str, idle_minutes: int) -> tuple[AccountIdentity, SessionRecord] | None:
        session_id = self._sessions_by_hash.get(token_hash)
        session = self._sessions.get(session_id) if session_id else None
        now = utc_now()
        if session is None or session.revoked_at is not None or now >= session.idle_expires_at or now >= session.absolute_expires_at:
            return None
        user = self._users.get(session.user_id)
        if user is None or user.status != "active":
            return None
        session.last_seen_at = now
        session.idle_expires_at = min(now + timedelta(minutes=idle_minutes), session.absolute_expires_at)
        return self._identity(user), session

    def revoke_session(self, session_id: str, reason: str) -> bool:
        session = self._sessions.get(session_id)
        if session is None or session.revoked_at is not None:
            return False
        session.revoked_at = utc_now()
        session.revoke_reason = reason
        self._record_security_event("auth.session_revoked", "success", None, session.user_id, {"session_id": session_id, "reason": reason})
        return True

    def revoke_user_sessions(self, user_id: str, reason: str) -> int:
        count = 0
        for session in self._sessions.values():
            if session.user_id == user_id and session.revoked_at is None:
                session.revoked_at = utc_now()
                session.revoke_reason = reason
                count += 1
        return count

    def expire_session(self, session_id: str) -> None:
        session = self._sessions[session_id]
        session.idle_expires_at = utc_now() - timedelta(seconds=1)

    def list_users(self) -> list[dict]:
        return [{"id": user.id, "username": user.username, "display_name": user.display_name, "roles": sorted(user.roles), "status": user.status, "failed_login_count": user.failed_login_count, "locked_until": user.locked_until.isoformat() if user.locked_until else None, "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None} for user in self._users.values()]

    def list_roles(self) -> list[dict]:
        return [{"code": code, "permissions": sorted(permissions)} for code, permissions in ROLE_PERMISSIONS.items()]

    def list_sessions(self) -> list[dict]:
        return [{"id": session.id, "user_id": session.user_id, "created_at": session.created_at.isoformat(), "idle_expires_at": session.idle_expires_at.isoformat(), "absolute_expires_at": session.absolute_expires_at.isoformat(), "revoked_at": session.revoked_at.isoformat() if session.revoked_at else None} for session in self._sessions.values()]

    def create_user(self, username: str, display_name: str, password: str, roles: set[str], actor_id: str) -> dict:
        with self._lock:
            if username.casefold() in self._usernames:
                raise ValueError("duplicate_username")
            if not roles or any(role not in ROLE_PERMISSIONS for role in roles):
                raise ValueError("invalid_role")
            user = self.add_user(username, password, roles, display_name=display_name)
            self._record_security_event("account.created", "success", actor_id, user.id, {"username": username, "roles": sorted(roles)})
            return next(item for item in self.list_users() if item["id"] == user.id)

    def set_user_roles(self, user_id: str, roles: set[str], actor_id: str) -> dict:
        if not roles or any(role not in ROLE_PERMISSIONS for role in roles):
            raise ValueError("invalid_role")
        user = self._users.get(user_id)
        if user is None:
            raise KeyError(user_id)
        user.roles = frozenset(roles)
        self.revoke_user_sessions(user_id, "roles_changed")
        self._record_security_event("account.roles_changed", "success", actor_id, user_id, {"roles": sorted(roles), "sessions_revoked": True})
        return next(item for item in self.list_users() if item["id"] == user_id)

    def disable_user(self, user_id: str, actor_id: str) -> bool:
        user = self._users.get(user_id)
        if user is None:
            return False
        user.status = "disabled"
        self.revoke_user_sessions(user_id, "account_disabled")
        self._record_security_event("account.disabled", "success", actor_id, user_id, {"sessions_revoked": True})
        return True

    def bootstrap_admin(self, username: str, display_name: str, password: str) -> dict:
        with self._lock:
            if any("admin" in user.roles for user in self._users.values()):
                self._record_security_event("auth.bootstrap_admin", "rejected", None, None, {"reason": "admin_already_exists"})
                raise ValueError("admin_already_exists")
            account = self.create_user(username, display_name, password, {"admin"}, "bootstrap")
            self._record_security_event("auth.bootstrap_admin", "success", account["id"], account["id"], {"username": username})
            return account

    def reset_demo_passwords(self, usernames: list[str], password: str) -> list[dict]:
        normalized = list(dict.fromkeys(username.strip().casefold() for username in usernames if username.strip()))
        if not normalized or not password:
            raise ValueError("demo_password_reset_environment_invalid")
        with self._lock:
            records = [self._users[self._usernames[username]] for username in normalized if username in self._usernames]
            if len(records) != len(normalized):
                raise ValueError("unknown_username")
            reset_accounts: list[dict] = []
            for record in records:
                record.password_hash = hash_password(password)
                record.failed_login_count = 0
                record.locked_until = None
                revoked_count = self.revoke_user_sessions(record.id, "demo_password_reset")
                self._record_security_event(
                    "auth.demo_password_reset",
                    "success",
                    None,
                    record.id,
                    {"username": record.username, "sessions_revoked": revoked_count},
                )
                reset_accounts.append({"id": record.id, "username": record.username, "sessions_revoked": revoked_count})
            return reset_accounts

    def sync_demo_accounts(self, password: str) -> dict:
        if len(password) < 6:
            raise ValueError("demo_account_sync_environment_invalid")
        specifications = (
            ("Steven", "Steven", "operator"),
            ("approve", "审批人", "approver"),
        )
        with self._lock:
            old_users = list(self._users.values())
            old_session_count = len(self._sessions)
            targets: dict[str, UserRecord] = {}
            for username, display_name, role in specifications:
                existing_id = self._usernames.get(username.casefold())
                record = self._users.get(existing_id) if existing_id else None
                if record is None:
                    record = UserRecord(
                        id=str(uuid4()),
                        username=username,
                        display_name=display_name,
                        password_hash=hash_password(password),
                        roles=frozenset({role}),
                    )
                else:
                    record.username = username
                    record.display_name = display_name
                    record.password_hash = hash_password(password)
                    record.roles = frozenset({role})
                    record.status = "active"
                    record.failed_login_count = 0
                    record.locked_until = None
                targets[role] = record
            self._users = {record.id: record for record in targets.values()}
            self._usernames = {record.username.casefold(): record.id for record in targets.values()}
            self._sessions.clear()
            self._sessions_by_hash.clear()
            self._record_security_event(
                "auth.demo_accounts_synchronized",
                "success",
                targets["operator"].id,
                None,
                {
                    "previous_user_count": len(old_users),
                    "current_user_count": len(targets),
                    "sessions_revoked": old_session_count,
                    "accounts": [
                        {"username": record.username, "display_name": record.display_name, "role": role}
                        for role, record in targets.items()
                    ],
                },
            )
            return {
                "previous_user_count": len(old_users),
                "current_user_count": len(targets),
                "sessions_revoked": old_session_count,
                "accounts": [
                    {"id": record.id, "username": record.username, "display_name": record.display_name, "roles": [role]}
                    for role, record in targets.items()
                ],
            }

    def list_security_events(self) -> list[dict]:
        return list(self._security_events)

    def record_security_event(self, event_type: str, outcome: str, actor_user_id: str | None, subject_user_id: str | None, details: dict) -> None:
        self._record_security_event(event_type, outcome, actor_user_id, subject_user_id, details)

    def _record_security_event(self, event_type: str, outcome: str, actor_user_id: str | None, subject_user_id: str | None, details: dict) -> None:
        self._security_events.append({
            "id": str(uuid4()),
            "event_type": event_type,
            "outcome": outcome,
            "actor_user_id": actor_user_id,
            "subject_user_id": subject_user_id,
            "occurred_at": utc_now().isoformat(),
            "details": details,
        })
        if self._platform_audit is not None:
            self._platform_audit.append(
                actor=actor_user_id or "anonymous",
                action=event_type,
                object_type="user" if subject_user_id else "security_event",
                object_id=subject_user_id or event_type,
                before_after={"before": None, "after": {"outcome": outcome, **details}},
            )

    @staticmethod
    def _identity(record: UserRecord) -> AccountIdentity:
        return AccountIdentity(record.id, record.username, record.display_name, record.roles, record.permissions)


class PostgresAuthRepository:
    _EXPECTED_USER_FOREIGN_KEYS = frozenset(
        {
            ("auth_security_events", "actor_user_id"),
            ("auth_security_events", "subject_user_id"),
            ("auth_sessions", "user_id"),
            ("files", "created_by"),
            ("platform_audit_events", "actor_user_id"),
            ("review_candidates", "reviewer_id"),
            ("steven_inventory_count_lines", "updated_by"),
            ("steven_inventory_counts", "created_by"),
            ("steven_inventory_counts", "updated_by"),
            ("steven_inventory_counts", "submitted_by"),
            ("steven_inventory_counts", "decided_by"),
            ("steven_inventory_items", "created_by"),
            ("steven_inventory_items", "updated_by"),
            ("steven_inventory_import_batches", "created_by"),
            ("steven_inventory_import_batches", "confirmed_by"),
            ("steven_inventory_versions", "created_by"),
            ("steven_quote_approvals", "submitted_by"),
            ("steven_quote_approvals", "decided_by"),
            ("steven_quote_audit_events", "actor_user_id"),
            ("steven_quote_import_batches", "confirmed_by"),
            ("steven_templates", "created_by"),
            ("steven_tender_jobs", "created_by"),
            ("steven_tender_jobs", "updated_by"),
            ("steven_tender_jobs", "submitted_by"),
            ("steven_tender_jobs", "decided_by"),
            ("steven_tender_suppliers", "created_by"),
            ("steven_tender_versions", "created_by"),
            ("user_notifications", "actor_user_id"),
            ("user_notifications", "recipient_user_id"),
            ("user_preferences", "user_id"),
            ("user_roles", "assigned_by"),
            ("user_roles", "user_id"),
        }
    )
    _OPERATOR_USER_REFERENCES = (
        ("files", "created_by"),
        ("review_candidates", "reviewer_id"),
        ("steven_inventory_count_lines", "updated_by"),
        ("steven_inventory_counts", "created_by"),
        ("steven_inventory_counts", "updated_by"),
        ("steven_inventory_counts", "submitted_by"),
        ("steven_inventory_items", "created_by"),
        ("steven_inventory_items", "updated_by"),
        ("steven_inventory_import_batches", "created_by"),
        ("steven_inventory_import_batches", "confirmed_by"),
        ("steven_inventory_versions", "created_by"),
        ("steven_quote_approvals", "submitted_by"),
        ("steven_quote_import_batches", "confirmed_by"),
        ("steven_templates", "created_by"),
        ("steven_tender_jobs", "created_by"),
        ("steven_tender_jobs", "updated_by"),
        ("steven_tender_jobs", "submitted_by"),
        ("steven_tender_suppliers", "created_by"),
        ("steven_tender_versions", "created_by"),
    )
    _APPROVER_USER_REFERENCES = (
        ("steven_inventory_counts", "decided_by"),
        ("steven_quote_approvals", "decided_by"),
        ("steven_tender_jobs", "decided_by"),
    )

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def authenticate(self, username: str, password: str, max_failures: int, lock_minutes: int) -> AuthenticationResult:
        with self._engine.begin() as connection:
            row = connection.execute(text("SELECT id, username, display_name, password_hash, status, failed_login_count, locked_until FROM users WHERE lower(username)=lower(:username) FOR UPDATE"), {"username": username}).mappings().first()
            now = utc_now()
            if row is None:
                self._insert_security_event(connection, "auth.login_failed", "rejected", None, None, {"reason": "invalid_credentials", "username": username.casefold()})
                return AuthenticationResult("invalid_credentials")
            if row["status"] != "active":
                self._insert_security_event(connection, "auth.login_failed", "rejected", None, row["id"], {"reason": "account_disabled"})
                return AuthenticationResult("disabled")
            if row["locked_until"] and now < row["locked_until"]:
                self._insert_security_event(connection, "auth.login_failed", "rejected", None, row["id"], {"reason": "account_locked"})
                return AuthenticationResult("locked")
            if not verify_password(password, row["password_hash"]):
                failed_count = row["failed_login_count"] + 1
                locked_until = now + timedelta(minutes=lock_minutes) if failed_count >= max_failures else None
                connection.execute(text("UPDATE users SET failed_login_count=:count,locked_until=:locked_until,updated_at=:now WHERE id=:id"), {"count": failed_count, "locked_until": locked_until, "now": now, "id": row["id"]})
                self._insert_security_event(connection, "auth.login_failed", "rejected", None, row["id"], {"reason": "invalid_credentials", "failed_login_count": failed_count, "locked": locked_until is not None})
                return AuthenticationResult("locked" if locked_until else "invalid_credentials")
            connection.execute(text("UPDATE users SET failed_login_count=0,locked_until=NULL,last_login_at=:now,updated_at=:now WHERE id=:id"), {"now": now, "id": row["id"]})
            identity = self._identity_for_user(connection, row["id"], row["username"], row["display_name"])
            self._insert_security_event(connection, "auth.login_succeeded", "success", row["id"], row["id"], {})
            return AuthenticationResult("success", identity)

    def create_session(self, user_id: str, token_hash: str, idle_minutes: int, absolute_hours: int) -> SessionRecord:
        now = utc_now(); record = SessionRecord(str(uuid4()), user_id, token_hash, now, now, now + timedelta(minutes=idle_minutes), now + timedelta(hours=absolute_hours))
        with self._engine.begin() as connection:
            connection.execute(text("INSERT INTO auth_sessions (id,user_id,token_hash,created_at,last_seen_at,idle_expires_at,absolute_expires_at,is_active) VALUES (:id,:user_id,:token_hash,:created_at,:last_seen_at,:idle_expires_at,:absolute_expires_at,true)"), record.__dict__)
        return record

    def resolve_session(self, token_hash: str, idle_minutes: int) -> tuple[AccountIdentity, SessionRecord] | None:
        now = utc_now()
        with self._engine.begin() as connection:
            row = connection.execute(text("SELECT s.*, u.username, u.display_name, u.status AS user_status FROM auth_sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=:token_hash FOR UPDATE"), {"token_hash": token_hash}).mappings().first()
            if row is None or not row["is_active"] or row["revoked_at"] is not None or row["user_status"] != "active" or now >= row["idle_expires_at"] or now >= row["absolute_expires_at"]:
                return None
            next_idle = min(now + timedelta(minutes=idle_minutes), row["absolute_expires_at"])
            connection.execute(text("UPDATE auth_sessions SET last_seen_at=:now,idle_expires_at=:idle WHERE id=:id"), {"now": now, "idle": next_idle, "id": row["id"]})
            identity = self._identity_for_user(connection, row["user_id"], row["username"], row["display_name"])
            session = SessionRecord(row["id"], row["user_id"], row["token_hash"], row["created_at"], now, next_idle, row["absolute_expires_at"], row["revoked_at"], row["revoke_reason"])
            return identity, session

    def revoke_session(self, session_id: str, reason: str) -> bool:
        with self._engine.begin() as connection:
            session = connection.execute(text("SELECT user_id FROM auth_sessions WHERE id=:id"), {"id": session_id}).mappings().first()
            result = connection.execute(text("UPDATE auth_sessions SET revoked_at=now(),revoke_reason=:reason,is_active=false WHERE id=:id AND revoked_at IS NULL"), {"reason": reason, "id": session_id})
            if result.rowcount and session:
                self._insert_security_event(connection, "auth.session_revoked", "success", None, session["user_id"], {"session_id": session_id, "reason": reason})
            return bool(result.rowcount)

    def list_users(self) -> list[dict]:
        with self._engine.connect() as connection:
            return [dict(row) for row in connection.execute(text("SELECT id,username,display_name,email,status,created_at,updated_at FROM users ORDER BY username")).mappings()]

    def list_roles(self) -> list[dict]:
        with self._engine.connect() as connection:
            return [dict(row) for row in connection.execute(text("SELECT id,code,name,status FROM roles ORDER BY code")).mappings()]

    def list_sessions(self) -> list[dict]:
        with self._engine.connect() as connection:
            return [dict(row) for row in connection.execute(text("SELECT id,user_id,created_at,last_seen_at,idle_expires_at,absolute_expires_at,revoked_at,revoke_reason FROM auth_sessions ORDER BY created_at DESC")).mappings()]

    def create_user(self, username: str, display_name: str, password: str, roles: set[str], actor_id: str) -> dict:
        if not roles or any(role not in ROLE_PERMISSIONS for role in roles):
            raise ValueError("invalid_role")
        user_id = str(uuid4())
        try:
            with self._engine.begin() as connection:
                if connection.execute(text("SELECT 1 FROM users WHERE lower(username)=lower(:username)"), {"username": username}).first():
                    raise ValueError("duplicate_username")
                connection.execute(text("INSERT INTO users (id,username,display_name,password_hash,status,failed_login_count,created_at,updated_at) VALUES (:id,:username,:display_name,:password_hash,'active',0,now(),now())"), {"id": user_id, "username": username, "display_name": display_name, "password_hash": hash_password(password)})
                role_rows = connection.execute(text("SELECT id,code FROM roles WHERE code = ANY(:roles) AND status='active'"), {"roles": list(roles)}).mappings().all()
                if {row["code"] for row in role_rows} != roles:
                    raise ValueError("invalid_role")
                for row in role_rows:
                    connection.execute(text("INSERT INTO user_roles (user_id,role_id,assigned_by,assigned_at) VALUES (:user_id,:role_id,:actor_id,now())"), {"user_id": user_id, "role_id": row["id"], "actor_id": actor_id})
                self._insert_security_event(connection, "account.created", "success", actor_id, user_id, {"username": username, "roles": sorted(roles)})
        except IntegrityError as error:
            if self._is_username_conflict(error):
                raise ValueError("duplicate_username") from error
            raise
        return {"id": user_id, "username": username, "display_name": display_name, "roles": sorted(roles), "status": "active"}

    def set_user_roles(self, user_id: str, roles: set[str], actor_id: str) -> dict:
        if not roles or any(role not in ROLE_PERMISSIONS for role in roles):
            raise ValueError("invalid_role")
        with self._engine.begin() as connection:
            user = connection.execute(text("SELECT id,username,display_name,status FROM users WHERE id=:id FOR UPDATE"), {"id": user_id}).mappings().first()
            if user is None:
                raise KeyError(user_id)
            role_rows = connection.execute(text("SELECT id,code FROM roles WHERE code = ANY(:roles) AND status='active'"), {"roles": list(roles)}).mappings().all()
            if {row["code"] for row in role_rows} != roles:
                raise ValueError("invalid_role")
            connection.execute(text("DELETE FROM user_roles WHERE user_id=:user_id"), {"user_id": user_id})
            for row in role_rows:
                connection.execute(text("INSERT INTO user_roles (user_id,role_id,assigned_by,assigned_at) VALUES (:user_id,:role_id,:actor_id,now())"), {"user_id": user_id, "role_id": row["id"], "actor_id": actor_id})
            connection.execute(text("UPDATE auth_sessions SET revoked_at=now(),revoke_reason='roles_changed',is_active=false WHERE user_id=:user_id AND revoked_at IS NULL"), {"user_id": user_id})
            self._insert_security_event(connection, "account.roles_changed", "success", actor_id, user_id, {"roles": sorted(roles), "sessions_revoked": True})
        return {"id": user_id, "username": user["username"], "display_name": user["display_name"], "roles": sorted(roles), "status": user["status"]}

    def disable_user(self, user_id: str, actor_id: str) -> bool:
        with self._engine.begin() as connection:
            result = connection.execute(text("UPDATE users SET status='disabled',updated_at=now() WHERE id=:id AND status<>'disabled'"), {"id": user_id})
            if not result.rowcount:
                return False
            connection.execute(text("UPDATE auth_sessions SET revoked_at=now(),revoke_reason='account_disabled',is_active=false WHERE user_id=:user_id AND revoked_at IS NULL"), {"user_id": user_id})
            self._insert_security_event(connection, "account.disabled", "success", actor_id, user_id, {"sessions_revoked": True})
            return True

    def bootstrap_admin(self, username: str, display_name: str, password: str) -> dict:
        user_id = str(uuid4())
        rejection: str | None = None
        try:
            with self._engine.begin() as connection:
                connection.execute(text("SELECT pg_advisory_xact_lock(202607160004)"))
                existing = connection.execute(text("SELECT 1 FROM user_roles ur JOIN roles r ON r.id=ur.role_id WHERE r.code='admin' LIMIT 1")).first()
                if existing:
                    rejection = "admin_already_exists"
                elif connection.execute(text("SELECT 1 FROM users WHERE lower(username)=lower(:username)"), {"username": username}).first():
                    rejection = "duplicate_username"
                else:
                    role = connection.execute(text("SELECT id FROM roles WHERE code='admin' AND status='active' FOR UPDATE")).mappings().first()
                    if role is None:
                        raise RuntimeError("Active admin role is missing; run migrations first")
                    connection.execute(text("INSERT INTO users (id,username,display_name,password_hash,status,failed_login_count,created_at,updated_at) VALUES (:id,:username,:display_name,:password_hash,'active',0,now(),now())"), {"id": user_id, "username": username, "display_name": display_name, "password_hash": hash_password(password)})
                    connection.execute(text("INSERT INTO user_roles (user_id,role_id,assigned_by,assigned_at) VALUES (:user_id,:role_id,NULL,now())"), {"user_id": user_id, "role_id": role["id"]})
                    self._insert_security_event(connection, "auth.bootstrap_admin", "success", user_id, user_id, {"username": username})
        except IntegrityError as error:
            if self._is_username_conflict(error):
                rejection = "duplicate_username"
            else:
                raise
        if rejection:
            with self._engine.begin() as connection:
                self._insert_security_event(connection, "auth.bootstrap_admin", "rejected", None, None, {"reason": rejection})
            raise ValueError(rejection)
        return {"id": user_id, "username": username, "display_name": display_name, "roles": ["admin"], "status": "active"}

    def reset_demo_passwords(self, usernames: list[str], password: str) -> list[dict]:
        normalized = list(dict.fromkeys(username.strip().casefold() for username in usernames if username.strip()))
        if not normalized or not password:
            raise ValueError("demo_password_reset_environment_invalid")
        with self._engine.begin() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT id, username
                    FROM users
                    WHERE lower(username) = ANY(:usernames)
                    FOR UPDATE
                    """
                ),
                {"usernames": normalized},
            ).mappings().all()
            if len(rows) != len(normalized):
                raise ValueError("unknown_username")
            reset_accounts: list[dict] = []
            for row in rows:
                password_hash = hash_password(password)
                connection.execute(
                    text(
                        """
                        UPDATE users
                        SET password_hash=:password_hash,
                            failed_login_count=0,
                            locked_until=NULL,
                            updated_at=now()
                        WHERE id=:user_id
                        """
                    ),
                    {"password_hash": password_hash, "user_id": row["id"]},
                )
                revoked = connection.execute(
                    text(
                        """
                        UPDATE auth_sessions
                        SET revoked_at=now(),
                            revoke_reason='demo_password_reset',
                            is_active=false
                        WHERE user_id=:user_id
                          AND revoked_at IS NULL
                          AND is_active=true
                        """
                    ),
                    {"user_id": row["id"]},
                )
                revoked_count = int(revoked.rowcount or 0)
                self._insert_security_event(
                    connection,
                    "auth.demo_password_reset",
                    "success",
                    None,
                    row["id"],
                    {"username": row["username"], "sessions_revoked": revoked_count},
                )
                reset_accounts.append({"id": row["id"], "username": row["username"], "sessions_revoked": revoked_count})
            return sorted(reset_accounts, key=lambda account: account["username"].casefold())

    def sync_demo_accounts(self, password: str) -> dict:
        if len(password) < 6:
            raise ValueError("demo_account_sync_environment_invalid")
        specifications = (
            ("Steven", "Steven", "operator"),
            ("approve", "审批人", "approver"),
        )
        with self._engine.begin() as connection:
            connection.execute(text("SELECT pg_advisory_xact_lock(202607170010)"))
            current_foreign_keys = {
                (row["table_name"], row["column_name"])
                for row in connection.execute(
                    text(
                        """
                        SELECT child.relname AS table_name,
                               child_attribute.attname AS column_name
                          FROM pg_constraint constraint_row
                          JOIN pg_class child ON child.oid = constraint_row.conrelid
                          JOIN pg_class parent ON parent.oid = constraint_row.confrelid
                          JOIN unnest(constraint_row.conkey) WITH ORDINALITY child_key(attnum, ordinality) ON true
                          JOIN unnest(constraint_row.confkey) WITH ORDINALITY parent_key(attnum, ordinality)
                            ON parent_key.ordinality = child_key.ordinality
                          JOIN pg_attribute child_attribute
                            ON child_attribute.attrelid = child.oid
                           AND child_attribute.attnum = child_key.attnum
                          JOIN pg_attribute parent_attribute
                            ON parent_attribute.attrelid = parent.oid
                           AND parent_attribute.attnum = parent_key.attnum
                         WHERE constraint_row.contype = 'f'
                           AND parent.relname = 'users'
                           AND parent_attribute.attname = 'id'
                        """
                    )
                ).mappings()
            }
            if current_foreign_keys != self._EXPECTED_USER_FOREIGN_KEYS:
                raise RuntimeError(
                    "users foreign-key inventory changed; account synchronization requires governance review"
                )

            role_rows = connection.execute(
                text(
                    """
                    SELECT id, code
                      FROM roles
                     WHERE code = ANY(:roles)
                       AND status = 'active'
                     FOR UPDATE
                    """
                ),
                {"roles": ["operator", "approver"]},
            ).mappings().all()
            roles_by_code = {row["code"]: row["id"] for row in role_rows}
            if set(roles_by_code) != {"operator", "approver"}:
                raise RuntimeError("required active Demo roles are missing; run migrations first")

            previous_users = connection.execute(
                text("SELECT id, username FROM users ORDER BY id FOR UPDATE")
            ).mappings().all()
            previous_role_rows = connection.execute(
                text(
                    """
                    SELECT ur.user_id, r.code
                      FROM user_roles ur
                      JOIN roles r ON r.id = ur.role_id
                     ORDER BY ur.user_id, r.code
                    """
                )
            ).mappings().all()
            roles_by_user_id: dict[str, set[str]] = {}
            for role_row in previous_role_rows:
                roles_by_user_id.setdefault(role_row["user_id"], set()).add(role_row["code"])
            previous_user_count = len(previous_users)
            historical_by_id = {
                row["id"]: {
                    "username": row["username"],
                    "roles": roles_by_user_id.get(row["id"], set()),
                }
                for row in previous_users
            }

            targets: dict[str, dict] = {}
            for username, display_name, role in specifications:
                existing = connection.execute(
                    text("SELECT id FROM users WHERE lower(username)=lower(:username) FOR UPDATE"),
                    {"username": username},
                ).mappings().first()
                user_id = existing["id"] if existing else str(uuid4())
                if existing:
                    connection.execute(
                        text(
                            """
                            UPDATE users
                               SET username=:username,
                                   display_name=:display_name,
                                   password_hash=:password_hash,
                                   status='active',
                                   failed_login_count=0,
                                   locked_until=NULL,
                                   updated_at=now()
                             WHERE id=:user_id
                            """
                        ),
                        {
                            "username": username,
                            "display_name": display_name,
                            "password_hash": hash_password(password),
                            "user_id": user_id,
                        },
                    )
                else:
                    connection.execute(
                        text(
                            """
                            INSERT INTO users
                                (id,username,display_name,password_hash,status,failed_login_count,created_at,updated_at)
                            VALUES
                                (:user_id,:username,:display_name,:password_hash,'active',0,now(),now())
                            """
                        ),
                        {
                            "user_id": user_id,
                            "username": username,
                            "display_name": display_name,
                            "password_hash": hash_password(password),
                        },
                    )
                targets[role] = {
                    "id": user_id,
                    "username": username,
                    "display_name": display_name,
                    "role": role,
                }

            target_ids = {target["id"] for target in targets.values()}
            old_user_ids = [user_id for user_id in historical_by_id if user_id not in target_ids]
            if old_user_ids:
                connection.execute(
                    text(
                        """
                        UPDATE platform_audit_events event
                           SET actor_label=coalesce(event.actor_label, source.username),
                               before_after=event.before_after || jsonb_build_object(
                                   'demo_account_sync_original_actor',
                                   jsonb_build_object('user_id', source.id, 'username', source.username)
                               )
                          FROM users source
                         WHERE event.actor_user_id=source.id
                           AND source.id=ANY(:old_user_ids)
                        """
                    ),
                    {"old_user_ids": old_user_ids},
                )
                connection.execute(
                    text(
                        """
                        UPDATE auth_security_events event
                           SET details=coalesce(event.details, '{}'::jsonb)
                               || jsonb_strip_nulls(
                                   jsonb_build_object(
                                       'demo_account_sync_original_actor',
                                       CASE
                                           WHEN event.actor_user_id=ANY(:old_user_ids)
                                           THEN (
                                               SELECT jsonb_build_object(
                                                   'user_id', actor.id,
                                                   'username', actor.username
                                               )
                                                 FROM users actor
                                                WHERE actor.id=event.actor_user_id
                                           )
                                       END,
                                       'demo_account_sync_original_subject',
                                       CASE
                                           WHEN event.subject_user_id=ANY(:old_user_ids)
                                           THEN (
                                               SELECT jsonb_build_object(
                                                   'user_id', subject.id,
                                                   'username', subject.username
                                               )
                                                 FROM users subject
                                                WHERE subject.id=event.subject_user_id
                                           )
                                       END
                                   )
                               )
                         WHERE event.actor_user_id=ANY(:old_user_ids)
                            OR event.subject_user_id=ANY(:old_user_ids)
                        """
                    ),
                    {"old_user_ids": old_user_ids},
                )
                connection.execute(
                    text(
                        """
                        UPDATE steven_quote_audit_events event
                           SET before_after=event.before_after || jsonb_build_object(
                               'demo_account_sync_original_actor',
                               jsonb_build_object('user_id', source.id, 'username', source.username)
                           )
                          FROM users source
                         WHERE event.actor_user_id=source.id
                           AND source.id=ANY(:old_user_ids)
                        """
                    ),
                    {"old_user_ids": old_user_ids},
                )

            revoked_sessions = connection.execute(text("DELETE FROM auth_sessions")).rowcount or 0
            connection.execute(text("DELETE FROM user_roles"))

            for table_name, column_name in self._OPERATOR_USER_REFERENCES:
                connection.execute(
                    text(f'UPDATE "{table_name}" SET "{column_name}"=:target_id WHERE "{column_name}" IS NOT NULL'),
                    {"target_id": targets["operator"]["id"]},
                )
            for table_name, column_name in self._APPROVER_USER_REFERENCES:
                connection.execute(
                    text(f'UPDATE "{table_name}" SET "{column_name}"=:target_id WHERE "{column_name}" IS NOT NULL'),
                    {"target_id": targets["approver"]["id"]},
                )

            audit_targets: dict[str, str] = {}
            for user_id, history in historical_by_id.items():
                roles = history["roles"]
                if "approver" in roles and not ({"operator", "steven", "admin"} & roles):
                    audit_targets[user_id] = targets["approver"]["id"]
                else:
                    audit_targets[user_id] = targets["operator"]["id"]
            for target in targets.values():
                audit_targets[target["id"]] = target["id"]

            if old_user_ids:
                connection.execute(
                    text("DELETE FROM user_preferences WHERE user_id=ANY(:old_user_ids)"),
                    {"old_user_ids": old_user_ids},
                )

            for old_user_id, target_user_id in audit_targets.items():
                connection.execute(
                    text(
                        """
                        UPDATE auth_security_events
                           SET actor_user_id=:target_user_id
                         WHERE actor_user_id=:old_user_id
                        """
                    ),
                    {"target_user_id": target_user_id, "old_user_id": old_user_id},
                )
                connection.execute(
                    text(
                        """
                        UPDATE auth_security_events
                           SET subject_user_id=:target_user_id
                         WHERE subject_user_id=:old_user_id
                        """
                    ),
                    {"target_user_id": target_user_id, "old_user_id": old_user_id},
                )
                connection.execute(
                    text(
                        """
                        UPDATE platform_audit_events
                           SET actor_user_id=:target_user_id
                         WHERE actor_user_id=:old_user_id
                        """
                    ),
                    {"target_user_id": target_user_id, "old_user_id": old_user_id},
                )
                connection.execute(
                    text(
                        """
                        UPDATE steven_quote_audit_events
                           SET actor_user_id=:target_user_id
                         WHERE actor_user_id=:old_user_id
                        """
                    ),
                    {"target_user_id": target_user_id, "old_user_id": old_user_id},
                )
                connection.execute(
                    text(
                        """
                        UPDATE user_notifications
                           SET actor_user_id=:target_user_id
                         WHERE actor_user_id=:old_user_id
                        """
                    ),
                    {"target_user_id": target_user_id, "old_user_id": old_user_id},
                )
                connection.execute(
                    text(
                        """
                        UPDATE user_notifications
                           SET recipient_user_id=:target_user_id
                         WHERE recipient_user_id=:old_user_id
                        """
                    ),
                    {"target_user_id": target_user_id, "old_user_id": old_user_id},
                )

            for role, target in targets.items():
                connection.execute(
                    text(
                        """
                        INSERT INTO user_roles (user_id,role_id,assigned_by,assigned_at)
                        VALUES (:user_id,:role_id,:assigned_by,now())
                        """
                    ),
                    {
                        "user_id": target["id"],
                        "role_id": roles_by_code[role],
                        "assigned_by": targets["operator"]["id"],
                    },
                )

            if old_user_ids:
                deleted_users = connection.execute(
                    text("DELETE FROM users WHERE id=ANY(:old_user_ids)"),
                    {"old_user_ids": old_user_ids},
                ).rowcount or 0
            else:
                deleted_users = 0

            remaining_users = connection.execute(text("SELECT count(*) FROM users")).scalar_one()
            remaining_role_rows = connection.execute(text("SELECT count(*) FROM user_roles")).scalar_one()
            if remaining_users != 2 or remaining_role_rows != 2:
                raise RuntimeError("Demo account synchronization did not converge to exactly two accounts")

            for table_name, column_name in self._EXPECTED_USER_FOREIGN_KEYS:
                dangling_reference_count = connection.execute(
                    text(
                        f"""
                        SELECT count(*)
                          FROM "{table_name}" child
                          LEFT JOIN users parent ON parent.id=child."{column_name}"
                         WHERE child."{column_name}" IS NOT NULL
                           AND parent.id IS NULL
                        """
                    )
                ).scalar_one()
                if dangling_reference_count:
                    raise RuntimeError(
                        f"users foreign-key remapping left dangling references in {table_name}.{column_name}"
                    )

            self._insert_security_event(
                connection,
                "auth.demo_accounts_synchronized",
                "success",
                targets["operator"]["id"],
                None,
                {
                    "previous_user_count": previous_user_count,
                    "current_user_count": 2,
                    "users_removed": int(deleted_users),
                    "sessions_revoked": int(revoked_sessions),
                    "accounts": [
                        {
                            "username": target["username"],
                            "display_name": target["display_name"],
                            "role": target["role"],
                        }
                        for target in targets.values()
                    ],
                },
            )
            return {
                "previous_user_count": previous_user_count,
                "current_user_count": 2,
                "users_removed": int(deleted_users),
                "sessions_revoked": int(revoked_sessions),
                "accounts": [
                    {
                        "id": target["id"],
                        "username": target["username"],
                        "display_name": target["display_name"],
                        "roles": [target["role"]],
                    }
                    for target in targets.values()
                ],
            }

    def list_security_events(self) -> list[dict]:
        with self._engine.connect() as connection:
            return [dict(row) for row in connection.execute(text("SELECT id,event_type,outcome,actor_user_id,subject_user_id,occurred_at,details FROM auth_security_events ORDER BY occurred_at")).mappings()]

    def record_security_event(self, event_type: str, outcome: str, actor_user_id: str | None, subject_user_id: str | None, details: dict) -> None:
        with self._engine.begin() as connection:
            self._insert_security_event(connection, event_type, outcome, actor_user_id, subject_user_id, details)

    @staticmethod
    def _insert_security_event(connection, event_type: str, outcome: str, actor_user_id: str | None, subject_user_id: str | None, details: dict) -> None:
        connection.execute(
            text("INSERT INTO auth_security_events (id,event_type,outcome,actor_user_id,subject_user_id,occurred_at,details) VALUES (:id,:event_type,:outcome,:actor_user_id,:subject_user_id,now(),CAST(:details AS jsonb))"),
            {"id": str(uuid4()), "event_type": event_type, "outcome": outcome, "actor_user_id": actor_user_id, "subject_user_id": subject_user_id, "details": json.dumps(details, ensure_ascii=False)},
        )
        connection.execute(
            text("""
                INSERT INTO platform_audit_events
                    (id,actor_user_id,actor_label,action,outcome,object_type,object_id,request_id,occurred_at,before_after)
                VALUES
                    (:id,:actor_user_id,:actor_label,:action,:outcome,:object_type,:object_id,:request_id,now(),CAST(:before_after AS jsonb))
            """),
            {
                "id": str(uuid4()),
                "actor_user_id": actor_user_id,
                "actor_label": None if actor_user_id else "anonymous",
                "action": event_type,
                "outcome": outcome,
                "object_type": "user" if subject_user_id else "security_event",
                "object_id": subject_user_id or event_type,
                "request_id": current_request_id(),
                "before_after": json.dumps({"before": None, "after": details}, ensure_ascii=False),
            },
        )

    @staticmethod
    def _is_username_conflict(error: IntegrityError) -> bool:
        constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
        return constraint in {"uq_users_username", "uq_users_username_lower"}

    @staticmethod
    def _identity_for_user(connection, user_id: str, username: str, display_name: str) -> AccountIdentity:
        rows = connection.execute(text("SELECT DISTINCT r.code AS role_code, p.code AS permission_code FROM user_roles ur JOIN roles r ON r.id=ur.role_id LEFT JOIN role_permissions rp ON rp.role_id=r.id LEFT JOIN permissions p ON p.id=rp.permission_id WHERE ur.user_id=:user_id AND r.status='active'"), {"user_id": user_id}).mappings()
        roles: set[str] = set(); permissions: set[str] = set()
        for row in rows:
            roles.add(row["role_code"])
            if row["permission_code"]:
                permissions.add(row["permission_code"])
        return AccountIdentity(user_id, username, display_name, frozenset(roles), frozenset(permissions))
