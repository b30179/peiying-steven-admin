from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DashboardMetric(BaseModel):
    key: str
    label: str
    value: int
    tone: Literal["warning", "danger", "neutral", "success"]
    detail: str


class ReviewFact(BaseModel):
    label: str
    value: str


class DashboardTodo(BaseModel):
    id: str
    module: Literal["tender", "quote", "inventory"]
    title: str
    detail: str
    status: str
    due_label: str
    action_label: str
    review_sources: list[ReviewFact]
    review_rules: list[ReviewFact]
    exception: str | None = None


class DashboardActivity(BaseModel):
    id: str
    action: str
    detail: str
    occurred_at: str


class DashboardModuleEntry(BaseModel):
    key: Literal["tenders", "quotes", "inventory"]
    title: str
    description: str
    exception_count: int = Field(ge=0)


class StevenDashboard(BaseModel):
    actor: str
    metrics: list[DashboardMetric]
    priority_todos: list[DashboardTodo] = Field(max_length=5)
    activities: list[DashboardActivity]
    modules: list[DashboardModuleEntry]
    ai_enabled: bool = False