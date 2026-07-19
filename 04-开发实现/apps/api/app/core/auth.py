from __future__ import annotations

import hashlib
from dataclasses import dataclass

from fastapi import Depends, Request

from app.core.api_response import ApiError
from app.core.permissions import ROLE_PERMISSIONS
from app.modules.accounts.repository import AccountIdentity, AuthRepository
from app.core.request_security import reject_legacy_identity_headers


@dataclass(frozen=True)
class CurrentPrincipal:
    user_id: str
    username: str
    display_name: str
    roles: frozenset[str]
    permissions: frozenset[str]
    session_id: str | None
    auth_mode: str

    @property
    def actor_id(self) -> str:
        return self.user_id


Actor = CurrentPrincipal


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def mock_principal(identity: str) -> CurrentPrincipal:
    role_sets = {
        "operator": frozenset({"operator"}),
        "steven": frozenset({"operator"}),
        "approver": frozenset({"approver"}),
        "admin": frozenset({"admin"}),
        "dual": frozenset({"operator", "approver"}),
    }
    roles = role_sets.get(identity)
    if roles is None:
        raise RuntimeError(f"Unsupported MOCK_IDENTITY: {identity}")
    permissions = frozenset().union(*(ROLE_PERMISSIONS[role] for role in roles))
    return CurrentPrincipal(f"mock-{identity}", f"{identity}.mock", f"{identity.title()} Mock", roles, permissions, None, "mock")


async def current_principal(request: Request) -> CurrentPrincipal:
    reject_legacy_identity_headers(request)
    settings = request.app.state.settings
    if settings.auth_mode == "mock":
        return mock_principal(settings.mock_identity)
    token = request.cookies.get(settings.session_cookie_name)
    repository: AuthRepository = request.app.state.auth_repository
    if not token:
        repository.record_security_event(
            "auth.session_rejected",
            "rejected",
            None,
            None,
            {"reason": "missing_session", "method": request.method, "path": request.url.path},
        )
        raise ApiError(401, "unauthenticated", "请先登录。")
    resolved = repository.resolve_session(hash_session_token(token), settings.session_idle_minutes)
    if resolved is None:
        repository.record_security_event(
            "auth.session_rejected",
            "rejected",
            None,
            None,
            {"reason": "invalid_expired_or_revoked", "method": request.method, "path": request.url.path},
        )
        raise ApiError(401, "invalid_session", "会话无效、已过期或已撤销。")
    identity, session = resolved
    return CurrentPrincipal(identity.user_id, identity.username, identity.display_name, identity.roles, identity.permissions, session.id, "session")


def require_permissions(*required: str):
    async def dependency(request: Request, principal: CurrentPrincipal = Depends(current_principal)) -> CurrentPrincipal:
        missing = [permission for permission in required if permission not in principal.permissions]
        if missing:
            repository: AuthRepository = request.app.state.auth_repository
            repository.record_security_event(
                "auth.authorization_rejected",
                "rejected",
                principal.user_id,
                principal.user_id,
                {"missing_permissions": missing, "method": request.method, "path": request.url.path},
            )
            raise ApiError(403, "forbidden", "当前账户无权执行此操作。", {"missing_permissions": missing})
        return principal
    return dependency
