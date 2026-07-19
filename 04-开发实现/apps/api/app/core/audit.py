from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from threading import RLock
from typing import Any, Protocol
from uuid import uuid4

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import Connection, Engine, text

from app.core.audit_context import current_request_id


@dataclass(frozen=True)
class AuditEvent:
    id: str
    actor: str
    action: str
    object_type: str
    object_id: str
    timestamp: str
    request_id: str | None
    before_after: dict[str, Any]


class PlatformAuditRepository(Protocol):
    def append(self, *, actor: str, action: str, object_type: str, object_id: str, before_after: dict[str, Any], request_id: str | None = None) -> AuditEvent | dict[str, Any]: ...
    def list(self) -> list[dict[str, Any]]: ...
    def list_for_object(self, object_id: str) -> list[dict[str, Any]]: ...


class AuditRepository:
    """In-memory audit fixture, permitted only in development and tests."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []
        self._lock = RLock()

    def append(self, *, actor: str, action: str, object_type: str, object_id: str, before_after: dict[str, Any], request_id: str | None = None) -> AuditEvent:
        event = AuditEvent(
            id=str(uuid4()),
            actor=actor,
            action=action,
            object_type=object_type,
            object_id=object_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            request_id=request_id or current_request_id(),
            before_after=before_after,
        )
        with self._lock:
            self._events.append(event)
        return event

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [asdict(event) for event in self._events]

    def list_for_object(self, object_id: str) -> list[dict[str, Any]]:
        def contains(value: Any) -> bool:
            if value == object_id:
                return True
            if isinstance(value, dict):
                return any(contains(item) for item in value.values())
            if isinstance(value, (list, tuple, set)):
                return any(contains(item) for item in value)
            return False

        with self._lock:
            return [asdict(event) for event in self._events if event.object_id == object_id or contains(event.before_after)]

    def checkpoint(self) -> int:
        with self._lock:
            return len(self._events)

    def rollback_to(self, checkpoint: int) -> None:
        with self._lock:
            del self._events[checkpoint:]


class PostgresAuditRepository:
    def __init__(self, bind: Engine | Connection) -> None:
        self._bind = bind

    @contextmanager
    def _connection(self, *, transactional: bool = False) -> Iterator[Connection]:
        if isinstance(self._bind, Connection):
            yield self._bind
        elif transactional:
            with self._bind.begin() as connection:
                yield connection
        else:
            with self._bind.connect() as connection:
                yield connection

    def append(self, *, actor: str, action: str, object_type: str, object_id: str, before_after: dict[str, Any], request_id: str | None = None) -> dict[str, Any]:
        event_id = str(uuid4())
        resolved_request_id = request_id or current_request_id()
        with self._connection(transactional=True) as connection:
            connection.execute(
                text("""
                    INSERT INTO platform_audit_events
                        (id,actor_user_id,actor_label,action,outcome,object_type,object_id,request_id,occurred_at,before_after)
                    VALUES
                        (:id,(SELECT id FROM users WHERE id=:actor),
                         CASE WHEN EXISTS (SELECT 1 FROM users WHERE id=:actor) THEN NULL ELSE :actor END,
                         :action,'success',:object_type,:object_id,:request_id,now(),CAST(:before_after AS jsonb))
                """),
                {
                    "id": event_id,
                    "actor": actor,
                    "action": action,
                    "object_type": object_type,
                    "object_id": object_id,
                    "request_id": resolved_request_id,
                    "before_after": json.dumps(before_after, ensure_ascii=False, default=str),
                },
            )
        return {"id": event_id, "request_id": resolved_request_id}

    def list(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(text("SELECT * FROM platform_audit_events ORDER BY occurred_at,id")).mappings().all()
        return [self._view(row) for row in rows]

    def list_for_object(self, object_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                text("SELECT * FROM platform_audit_events WHERE object_id=:object_id ORDER BY occurred_at,id"),
                {"object_id": object_id},
            ).mappings().all()
        return [self._view(row) for row in rows]

    @staticmethod
    def _view(row: Any) -> dict[str, Any]:
        return {
            "id": row["id"],
            "actor": row["actor_user_id"] or row["actor_label"] or "system",
            "action": row["action"],
            "outcome": row["outcome"],
            "object_type": row["object_type"],
            "object_id": row["object_id"],
            "timestamp": row["occurred_at"].isoformat(),
            "request_id": row["request_id"],
            "before_after": row["before_after"],
        }


development_audit_repository = AuditRepository()
