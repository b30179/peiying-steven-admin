from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.audit_context import reset_request_id, set_request_id


REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details: Mapping[str, Any] | None = None) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = dict(details or {})


def request_id_for(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def success(request: Request, data: Any, pagination: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {"data": data, "pagination": pagination, "request_id": request_id_for(request)}


def error_response(request: Request, error: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={
            "error": {
                "code": error.code,
                "message": error.message,
                "details": error.details,
                "request_id": request_id_for(request),
            }
        },
    )


async def request_id_middleware(request: Request, call_next: Any) -> Any:
    supplied_request_id = request.headers.get("X-Request-Id", "")
    request.state.request_id = supplied_request_id if REQUEST_ID_PATTERN.fullmatch(supplied_request_id) else str(uuid4())
    token = set_request_id(request.state.request_id)
    try:
        return await call_next(request)
    finally:
        reset_request_id(token)
