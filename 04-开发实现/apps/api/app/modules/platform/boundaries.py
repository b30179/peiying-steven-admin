from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.modules.platform.contracts import TaskStatus


@dataclass(frozen=True)
class AccountRef:
    account_id: str
    role: str


@dataclass(frozen=True)
class FileRef:
    file_id: str
    storage_key: str


@dataclass(frozen=True)
class TaskRef:
    task_id: str
    status: TaskStatus


class AccountsBoundary(Protocol):
    def resolve(self, account_id: str) -> AccountRef: ...


class FilesBoundary(Protocol):
    def get(self, file_id: str) -> FileRef: ...


class TasksBoundary(Protocol):
    def create(self, task_type: str) -> TaskRef: ...


class ApprovalsBoundary(Protocol):
    def request(self, object_type: str, object_id: str) -> str: ...


class NotificationsBoundary(Protocol):
    def notify(self, recipient_id: str, template: str) -> str: ...


class AuditBoundary(Protocol):
    def record(self, action: str, object_type: str, object_id: str) -> None: ...