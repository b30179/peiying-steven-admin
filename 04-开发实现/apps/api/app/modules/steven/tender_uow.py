from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Protocol

from sqlalchemy import Engine, text

from app.core.audit import AuditRepository, PostgresAuditRepository
from app.modules.steven.tender_repository import InMemoryTenderRepository


@dataclass(frozen=True)
class TenderTransaction:
    repository: object
    audit: object


class TenderUnitOfWork(Protocol):
    @contextmanager
    def begin(self, *, tender_id: str | None = None, version_id: str | None = None) -> Iterator[TenderTransaction]: ...


class InMemoryTenderUnitOfWork:
    def __init__(self, repository: InMemoryTenderRepository, audit: AuditRepository) -> None:
        self.repository = repository
        self.audit = audit

    @contextmanager
    def begin(self, *, tender_id: str | None = None, version_id: str | None = None) -> Iterator[TenderTransaction]:
        del tender_id, version_id
        checkpoint = self.audit.checkpoint()
        try:
            with self.repository.transaction():
                yield TenderTransaction(self.repository, self.audit)
        except Exception:
            self.audit.rollback_to(checkpoint)
            raise


class PostgresTenderUnitOfWork:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @contextmanager
    def begin(self, *, tender_id: str | None = None, version_id: str | None = None) -> Iterator[TenderTransaction]:
        from app.modules.steven.postgres_tender_repository import PostgresTenderRepository

        with self.engine.begin() as connection:
            if tender_id:
                connection.execute(
                    text("SELECT id FROM steven_tender_jobs WHERE id=:id FOR UPDATE"),
                    {"id": tender_id},
                )
            if version_id:
                connection.execute(
                    text("SELECT id FROM steven_tender_versions WHERE id=:id FOR UPDATE"),
                    {"id": version_id},
                )
            yield TenderTransaction(PostgresTenderRepository(connection), PostgresAuditRepository(connection))
