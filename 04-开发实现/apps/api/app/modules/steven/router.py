from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.core.api_response import success
from app.core.auth import Actor
from app.modules.steven.permissions import require_audit_reader, require_steven
from app.modules.steven.repository import StevenDashboardRepository
from app.modules.steven.service import StevenDashboardService

router = APIRouter(prefix="/api/v1/steven", tags=["steven"])
audit_router = APIRouter(prefix="/api/v1/audit", tags=["audit"])
dashboard_repository = StevenDashboardRepository()


@router.get("/dashboard")
async def get_dashboard(request: Request, actor: Actor = Depends(require_steven)) -> dict:
    service = StevenDashboardService(dashboard_repository, request.app.state.audit_repository)
    return success(request, service.get_dashboard(actor.actor_id).model_dump())


@audit_router.get("/events")
async def list_audit_events(request: Request, _: Actor = Depends(require_audit_reader)) -> dict:
    return success(request, request.app.state.audit_repository.list())
