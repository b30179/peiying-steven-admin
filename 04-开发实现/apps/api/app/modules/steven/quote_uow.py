from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Protocol

from sqlalchemy import Engine, text

from app.core.audit import AuditRepository
from app.modules.steven.quote_repository import StevenQuoteRepository


@dataclass(frozen=True)
class QuoteTransaction:
    repository: object
    audit: object


class QuoteUnitOfWork(Protocol):
    @contextmanager
    def begin(
        self,
        *,
        quote_id: str | None = None,
        batch_id: str | None = None,
        approval_id: str | None = None,
    ) -> Iterator[QuoteTransaction]: ...


class InMemoryQuoteUnitOfWork:
    def __init__(self, repository: StevenQuoteRepository, audit: AuditRepository) -> None:
        self.repository = repository
        self.audit = audit

    @contextmanager
    def begin(
        self,
        *,
        quote_id: str | None = None,
        batch_id: str | None = None,
        approval_id: str | None = None,
    ) -> Iterator[QuoteTransaction]:
        del quote_id, batch_id, approval_id
        checkpoint = self.audit.checkpoint()
        try:
            with self.repository.transaction():
                yield QuoteTransaction(self.repository, self.audit)
        except Exception:
            self.audit.rollback_to(checkpoint)
            raise


class PostgresQuoteUnitOfWork:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @contextmanager
    def begin(
        self,
        *,
        quote_id: str | None = None,
        batch_id: str | None = None,
        approval_id: str | None = None,
    ) -> Iterator[QuoteTransaction]:
        from app.modules.steven.postgres_quote_repository import PostgresQuoteAuditRepository, PostgresQuoteRepository

        with self.engine.begin() as connection:
            if quote_id:
                connection.execute(text("SELECT id FROM steven_quote_jobs WHERE id=:id FOR UPDATE"), {"id": quote_id})
            if batch_id:
                connection.execute(text("SELECT id FROM steven_quote_import_batches WHERE id=:id FOR UPDATE"), {"id": batch_id})
            if approval_id:
                connection.execute(text("SELECT id FROM steven_quote_approvals WHERE id=:id FOR UPDATE"), {"id": approval_id})
            yield QuoteTransaction(PostgresQuoteRepository(connection), PostgresQuoteAuditRepository(connection))
