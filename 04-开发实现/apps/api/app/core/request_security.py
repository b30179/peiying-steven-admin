from __future__ import annotations

import secrets
from urllib.parse import urlsplit

from fastapi import Request

from app.core.api_response import ApiError, error_response

LEGACY_IDENTITY_HEADERS = (
    "x-role",
    "x-actor",
    "x-acting-role",
    "x-acting-actor",
)
LEGACY_IDENTITY_ERROR_CODE = "legacy_identity_headers_forbidden"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
LOGIN_PATH = "/api/v1/auth/login"


def reject_legacy_identity_headers(request: Request) -> None:
    rejected = [name for name in LEGACY_IDENTITY_HEADERS if name in request.headers]
    if rejected:
        raise ApiError(
            400,
            LEGACY_IDENTITY_ERROR_CODE,
            "身份由服务端会话决定，不接受客户端身份或角色请求头。",
            {"rejected_headers": rejected},
        )


def _origin_from_referer(referer: str) -> str | None:
    parsed = urlsplit(referer)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def validate_origin(request: Request) -> None:
    settings = request.app.state.settings
    origin = request.headers.get("origin")
    candidate = origin.rstrip("/") if origin else _origin_from_referer(request.headers.get("referer", ""))
    if candidate is None or candidate not in settings.allowed_origins:
        raise ApiError(403, "origin_not_allowed", "请求来源不在允许清单内。")


def validate_csrf(request: Request) -> None:
    settings = request.app.state.settings
    session_token = request.cookies.get(settings.session_cookie_name)
    cookie_token = request.cookies.get(settings.csrf_cookie_name)
    header_token = request.headers.get(settings.csrf_header_name)
    if not session_token or not cookie_token or not header_token:
        raise ApiError(403, "csrf_validation_failed", "状态变更请求缺少有效的 CSRF 凭据。")
    if not secrets.compare_digest(cookie_token, header_token):
        raise ApiError(403, "csrf_validation_failed", "CSRF 凭据不匹配。")


async def request_security_middleware(request: Request, call_next):
    try:
        reject_legacy_identity_headers(request)
        settings = request.app.state.settings
        if settings.auth_mode == "session" and request.method in UNSAFE_METHODS:
            validate_origin(request)
            if request.url.path != LOGIN_PATH:
                validate_csrf(request)
    except ApiError as error:
        repository = getattr(request.app.state, "auth_repository", None)
        if repository is not None:
            repository.record_security_event(
                "auth.request_rejected",
                "rejected",
                None,
                None,
                {"code": error.code, "method": request.method, "path": request.url.path},
            )
        return error_response(request, error)
    return await call_next(request)
