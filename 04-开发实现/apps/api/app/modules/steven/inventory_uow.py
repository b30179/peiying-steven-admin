from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Protocol

from sqlalchemy import Engine, text

from app.core.audit import AuditRepository, PostgresAuditRepository
from app.modules.steven.inventory_repository import InMemoryInventoryRepository


@dataclass(frozen=True)
class InventoryTransaction:
    repository: object
    audit: object


class InventoryUnitOfWork(Protocol):
    @contextmanager
    def begin(
        self,
        *,
        item_id: str | None = None,
        count_id: str | None = None,
        version_id: str | None = None,
        import_batch_id: str | None = None,
    ) -> Iterator[InventoryTransaction]: ...


class InMemoryInventoryUnitOfWork:
    def __init__(self, repository: InMemoryInventoryRepository, audit: AuditRepository) -> None:
        self.repository = repository
        self.audit = audit

    @contextmanager
    def begin(self, **_) -> Iterator[InventoryTransaction]:
        checkpoint = self.audit.checkpoint()
        try:
            with self.repository.transaction():
                yield InventoryTransaction(self.repository, self.audit)
        except Exception:
            self.audit.rollback_to(checkpoint)
            raise


class PostgresInventoryUnitOfWork:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @contextmanager
    def begin(
        self,
        *,
        item_id: str | None = None,
        count_id: str | None = None,
        version_id: str | None = None,
        import_batch_id: str | None = None,
    ) -> Iterator[InventoryTransaction]:
        from app.modules.steven.postgres_inventory_repository import PostgresInventoryRepository

        with self.engine.begin() as connection:
            if item_id:
                connection.execute(
                    text("SELECT id FROM steven_inventory_items WHERE id=:id FOR UPDATE"),
                    {"id": item_id},
                )
            if count_id:
                connection.execute(
                    text("SELECT id FROM steven_inventory_counts WHERE id=:id FOR UPDATE"),
                    {"id": count_id},
                )
            if version_id:
                connection.execute(
                    text("SELECT id FROM steven_inventory_versions WHERE id=:id FOR UPDATE"),
                    {"id": version_id},
                )
            if import_batch_id:
                connection.execute(
                    text(
                        "SELECT id FROM steven_inventory_import_batches WHERE id=:id FOR UPDATE"
                    ),
                    {"id": import_batch_id},
                )
            yield InventoryTransaction(PostgresInventoryRepository(connection), PostgresAuditRepository(connection))
