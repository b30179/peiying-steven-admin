from __future__ import annotations

from app.core.audit import PlatformAuditRepository
from app.modules.steven.repository import StevenDashboardRepository
from app.modules.steven.schemas import StevenDashboard


class StevenDashboardService:
    def __init__(self, repository: StevenDashboardRepository, audit: PlatformAuditRepository) -> None:
        self._repository = repository
        self._audit = audit

    def get_dashboard(self, actor: str) -> StevenDashboard:
        dashboard = self._repository.dashboard_for(actor)
        self._audit.append(
            actor=actor,
            action="dashboard.view",
            object_type="steven_dashboard",
            object_id="overview",
            before_after={"before": None, "after": {"ai_enabled": dashboard.ai_enabled}},
        )
        return dashboard
