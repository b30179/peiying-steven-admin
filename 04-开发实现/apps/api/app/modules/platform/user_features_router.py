from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.core.api_response import ApiError, success
from app.core.auth import CurrentPrincipal, require_permissions
from app.core.permissions import NOTIFICATIONS_READ_OWN, NOTIFICATIONS_UPDATE_OWN, STEVEN_HISTORY_READ_SCOPED
from app.modules.platform.user_features import UserFeaturesService

router = APIRouter(prefix="/api/v1/steven", tags=["user-features"])


@router.get("/notifications")
async def list_notifications(
    request: Request,
    unread_only: bool = False,
    limit: int = 100,
    principal: CurrentPrincipal = Depends(require_permissions(NOTIFICATIONS_READ_OWN)),
) -> dict:
    service: UserFeaturesService = request.app.state.user_features
    records = service.list_notifications(principal.user_id, unread_only, limit)
    return success(request, records, {"page": 1, "page_size": len(records), "total": len(records)})


@router.get("/notifications/unread-count")
async def unread_count(
    request: Request,
    principal: CurrentPrincipal = Depends(require_permissions(NOTIFICATIONS_READ_OWN)),
) -> dict:
    service: UserFeaturesService = request.app.state.user_features
    return success(request, {"count": service.unread_count(principal.user_id)})


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    request: Request,
    notification_id: str,
    principal: CurrentPrincipal = Depends(require_permissions(NOTIFICATIONS_UPDATE_OWN)),
) -> dict:
    service: UserFeaturesService = request.app.state.user_features
    if not service.mark_notification_read(principal.user_id, notification_id):
        raise ApiError(404, "notification_not_found", "找不到通知。")
    return success(request, {"read": True})


@router.post("/notifications/read-all")
async def mark_all_notifications_read(
    request: Request,
    principal: CurrentPrincipal = Depends(require_permissions(NOTIFICATIONS_UPDATE_OWN)),
) -> dict:
    service: UserFeaturesService = request.app.state.user_features
    return success(request, {"updated": service.mark_all_read(principal.user_id)})


@router.get("/history")
async def list_history(
    request: Request,
    module: str | None = None,
    limit: int = 100,
    _: CurrentPrincipal = Depends(require_permissions(STEVEN_HISTORY_READ_SCOPED)),
) -> dict:
    if module not in {None, "", "s1", "s2", "s3"}:
        raise ApiError(422, "invalid_history_module", "歷史模組篩選值無效。")
    service: UserFeaturesService = request.app.state.user_features
    records = service.history(module or None, limit)
    return success(request, records, {"page": 1, "page_size": len(records), "total": len(records)})