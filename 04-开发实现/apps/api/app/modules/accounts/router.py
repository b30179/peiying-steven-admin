from __future__ import annotations

import secrets
import ipaddress

from fastapi import APIRouter, Depends, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.core.api_response import ApiError, success
from app.core.auth import CurrentPrincipal, current_principal, hash_session_token, require_permissions
from app.core.permissions import (
    ACCOUNTS_MANAGE,
    PASSWORD_CHANGE_OWN,
    PROFILE_READ_OWN,
    PROFILE_UPDATE_OWN,
    ROLES_MANAGE,
    SESSIONS_MANAGE,
)
from app.core.request_security import reject_legacy_identity_headers
from app.modules.accounts.repository import AuthRepository
from app.modules.platform.user_features import UserFeaturesService
from app.modules.accounts.schemas import (
    AccountCreateRequest,
    AccountRolesRequest,
    LoginRequest,
    PasswordChangeRequest,
    PrincipalView,
    UserSettingsUpdateRequest,
)

auth_router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
admin_router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def _principal_view(principal: CurrentPrincipal) -> PrincipalView:
    return PrincipalView(
        user_id=principal.user_id,
        username=principal.username,
        display_name=principal.display_name,
        roles=sorted(principal.roles),
        permissions=sorted(principal.permissions),
        auth_mode=principal.auth_mode,
    )


def _client_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    settings = request.app.state.settings
    try:
        peer_address = ipaddress.ip_address(peer)
    except ValueError:
        return peer
    trusted = any(peer_address in ipaddress.ip_network(cidr, strict=False) for cidr in settings.trusted_proxy_cidrs)
    if not trusted:
        return peer
    forwarded = request.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
    try:
        return str(ipaddress.ip_address(forwarded)) if forwarded else peer
    except ValueError:
        return peer


@auth_router.post("/login")
async def login(request: Request, payload: LoginRequest) -> JSONResponse:
    settings = request.app.state.settings
    reject_legacy_identity_headers(request)
    if settings.auth_mode != "session":
        raise ApiError(409, "session_login_disabled", "当前环境未启用本地 Session 登录。")
    rate_key = f"{_client_ip(request)}:{payload.username.strip().casefold()}"
    limiter = request.app.state.login_rate_limiter
    repository: AuthRepository = request.app.state.auth_repository
    if not limiter.allow(rate_key):
        repository.record_security_event("auth.login_rate_limited", "rejected", None, None, {"username": payload.username.strip().casefold()})
        raise ApiError(429, "login_rate_limited", "登录尝试过于频繁，请稍后再试。")
    result = repository.authenticate(payload.username.strip(), payload.password, settings.login_max_failures, settings.login_lock_minutes)
    if result.identity is None:
        limiter.record_failure(rate_key)
        raise ApiError(401, "invalid_credentials", "用户名或密码不正确。")
    limiter.clear(rate_key)
    identity = result.identity
    raw_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    session = repository.create_session(identity.user_id, hash_session_token(raw_token), settings.session_idle_minutes, settings.session_absolute_hours)
    principal = CurrentPrincipal(identity.user_id, identity.username, identity.display_name, identity.roles, identity.permissions, session.id, "session")
    request.app.state.audit_repository.append(actor=identity.user_id, action="auth.login", object_type="auth_session", object_id=session.id, before_after={"before": None, "after": {"user_id": identity.user_id}})
    response = JSONResponse(content=jsonable_encoder(success(request, _principal_view(principal).model_dump())))
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        max_age=settings.session_absolute_hours * 3600,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        max_age=settings.session_absolute_hours * 3600,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    return response


@auth_router.get("/settings")
async def get_settings(
    request: Request,
    principal: CurrentPrincipal = Depends(require_permissions(PROFILE_READ_OWN)),
) -> dict:
    service: UserFeaturesService = request.app.state.user_features
    return success(request, service.get_settings(principal.user_id))


@auth_router.patch("/settings")
async def update_settings(
    request: Request,
    payload: UserSettingsUpdateRequest,
    principal: CurrentPrincipal = Depends(require_permissions(PROFILE_UPDATE_OWN)),
) -> dict:
    service: UserFeaturesService = request.app.state.user_features
    result = service.update_settings(principal.user_id, payload.display_name, payload.locale, request.state.request_id)
    return success(request, result)


@auth_router.post("/change-password")
async def change_password(
    request: Request,
    payload: PasswordChangeRequest,
    principal: CurrentPrincipal = Depends(require_permissions(PASSWORD_CHANGE_OWN)),
) -> dict:
    service: UserFeaturesService = request.app.state.user_features
    service.change_password(principal.user_id, principal.session_id, payload.old_password, payload.new_password, request.state.request_id)
    return success(request, {"changed": True})

@auth_router.post("/logout")
async def logout(request: Request, principal: CurrentPrincipal = Depends(current_principal)) -> JSONResponse:
    settings = request.app.state.settings
    if principal.session_id is None:
        raise ApiError(409, "mock_logout_disabled", "开发 mock 身份没有可撤销的生产 Session。")
    repository: AuthRepository = request.app.state.auth_repository
    repository.revoke_session(principal.session_id, "user_logout")
    request.app.state.audit_repository.append(actor=principal.user_id, action="auth.logout", object_type="auth_session", object_id=principal.session_id, before_after={"before": {"active": True}, "after": {"active": False}})
    response = JSONResponse(content=jsonable_encoder(success(request, {"logged_out": True})))
    response.delete_cookie(settings.session_cookie_name, path="/", secure=settings.session_cookie_secure, httponly=True, samesite="lax")
    response.delete_cookie(settings.csrf_cookie_name, path="/", secure=settings.session_cookie_secure, httponly=False, samesite="lax")
    return response


@auth_router.get("/me")
async def me(request: Request, principal: CurrentPrincipal = Depends(current_principal)) -> dict:
    return success(request, _principal_view(principal).model_dump())


@admin_router.get("/accounts")
async def list_accounts(request: Request, _: CurrentPrincipal = Depends(require_permissions(ACCOUNTS_MANAGE))) -> dict:
    repository: AuthRepository = request.app.state.auth_repository
    return success(request, repository.list_users())


@admin_router.get("/roles")
async def list_roles(request: Request, _: CurrentPrincipal = Depends(require_permissions(ROLES_MANAGE))) -> dict:
    repository: AuthRepository = request.app.state.auth_repository
    return success(request, repository.list_roles())


@admin_router.get("/sessions")
async def list_sessions(request: Request, _: CurrentPrincipal = Depends(require_permissions(SESSIONS_MANAGE))) -> dict:
    repository: AuthRepository = request.app.state.auth_repository
    return success(request, jsonable_encoder(repository.list_sessions()))


@admin_router.post("/sessions/{session_id}/revoke")
async def revoke_session(request: Request, session_id: str, principal: CurrentPrincipal = Depends(require_permissions(SESSIONS_MANAGE))) -> dict:
    repository: AuthRepository = request.app.state.auth_repository
    if not repository.revoke_session(session_id, "admin_revoked"):
        raise ApiError(404, "session_not_found", "未找到可撤销的会话。")
    request.app.state.audit_repository.append(actor=principal.user_id, action="auth.session_revoke", object_type="auth_session", object_id=session_id, before_after={"before": {"active": True}, "after": {"active": False}})
    return success(request, {"revoked": True, "session_id": session_id})


@admin_router.post("/accounts", status_code=201)
async def create_account(request: Request, payload: AccountCreateRequest, principal: CurrentPrincipal = Depends(require_permissions(ACCOUNTS_MANAGE))) -> dict:
    repository: AuthRepository = request.app.state.auth_repository
    try:
        account = repository.create_user(payload.username.strip(), payload.display_name.strip(), payload.password, set(payload.roles), principal.user_id)
    except ValueError as error:
        code = str(error)
        if code == "duplicate_username":
            raise ApiError(409, code, "用户名已存在。") from error
        raise ApiError(422, "invalid_role", "角色代码无效。", {"roles": payload.roles}) from error
    request.app.state.audit_repository.append(actor=principal.user_id, action="account.create", object_type="user", object_id=account["id"], before_after={"before": None, "after": {"username": account["username"], "roles": account["roles"]}})
    return success(request, account)


@admin_router.put("/accounts/{user_id}/roles")
async def assign_account_roles(request: Request, user_id: str, payload: AccountRolesRequest, principal: CurrentPrincipal = Depends(require_permissions(ROLES_MANAGE))) -> dict:
    repository: AuthRepository = request.app.state.auth_repository
    try:
        account = repository.set_user_roles(user_id, set(payload.roles), principal.user_id)
    except KeyError as error:
        raise ApiError(404, "account_not_found", "未找到账户。") from error
    except ValueError as error:
        raise ApiError(422, "invalid_role", "角色代码无效。", {"roles": payload.roles}) from error
    request.app.state.audit_repository.append(actor=principal.user_id, action="account.roles_update", object_type="user", object_id=user_id, before_after={"before": None, "after": {"roles": account["roles"], "sessions_revoked": True}})
    return success(request, account)


@admin_router.post("/accounts/{user_id}/disable")
async def disable_account(request: Request, user_id: str, principal: CurrentPrincipal = Depends(require_permissions(ACCOUNTS_MANAGE))) -> dict:
    repository: AuthRepository = request.app.state.auth_repository
    if not repository.disable_user(user_id, principal.user_id):
        raise ApiError(404, "account_not_found", "未找到可停用账户。")
    request.app.state.audit_repository.append(actor=principal.user_id, action="account.disable", object_type="user", object_id=user_id, before_after={"before": {"status": "active"}, "after": {"status": "disabled", "sessions_revoked": True}})
    return success(request, {"disabled": True, "user_id": user_id})
