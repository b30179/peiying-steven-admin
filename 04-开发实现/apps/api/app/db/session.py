from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings


def create_postgres_engine(settings: Settings) -> Engine:
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required for PostgreSQL mode")
    return create_engine(settings.database_url, pool_pre_ping=True, future=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)
