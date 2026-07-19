from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from urllib.request import urlopen

from openpyxl import load_workbook
from sqlalchemy import text
from sqlalchemy.engine import make_url


PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = PROJECT_ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from app.core.audit import PostgresAuditRepository  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.main import LazyPostgresQuoteApplication, create_app  # noqa: E402
from app.modules.accounts.repository import PostgresAuthRepository  # noqa: E402


def emit(step: str, status: str, **details) -> None:
    print(json.dumps({"step": step, "status": status, **details}, ensure_ascii=False, default=str))


def main() -> int:
    settings = Settings.from_env()
    settings.validate()
    database_name = make_url(settings.database_url).database if settings.database_url else None
    if settings.app_env != "development" or settings.auth_mode != "session":
        raise RuntimeError("D1.1 requires APP_ENV=development and AUTH_MODE=session")
    if settings.demo_seed_enabled:
        raise RuntimeError("D1.1 forbids demo seed during runtime verification")
    if database_name != "puiying_steven_demo":
        raise RuntimeError("D1.1 may only connect to puiying_steven_demo")

    application = create_app(settings)
    if not isinstance(application.state.auth_repository, PostgresAuthRepository):
        raise RuntimeError("Session repository did not select PostgreSQL")
    if not isinstance(application.state.audit_repository, PostgresAuditRepository):
        raise RuntimeError("Platform audit repository did not select PostgreSQL")
    if not isinstance(application.state.quote_application, LazyPostgresQuoteApplication):
        raise RuntimeError("S2 repository did not select PostgreSQL")

    with application.state.postgres_engine.connect() as connection:
        database_probe = connection.execute(
            text("SELECT current_database(), current_user, (SELECT version_num FROM alembic_version)")
        ).one()
        table_counts = connection.execute(
            text(
                """
                SELECT
                    (SELECT count(*) FROM auth_sessions),
                    (SELECT count(*) FROM platform_audit_events),
                    (SELECT count(*) FROM steven_quote_jobs),
                    (SELECT count(*) FROM steven_quote_items),
                    (SELECT count(*) FROM steven_quote_suppliers),
                    (SELECT count(*) FROM steven_quote_offer_lines),
                    (SELECT count(*) FROM steven_quote_versions)
                """
            )
        ).one()

    quotes = application.state.quote_application.list_quotes()
    versions = {
        quote.id: application.state.quote_application.list_versions(quote.id)
        for quote in quotes
    }
    audits = application.state.audit_repository.list()
    sessions = application.state.auth_repository.list_sessions()

    ready_files = 0
    readable_files = 0
    for records in versions.values():
        for version in records:
            if version.status != "ready":
                continue
            ready_files += 1
            path = Path(settings.file_storage_root) / version.storage_key
            if path.is_file():
                workbook = load_workbook(path, read_only=False, data_only=False)
                workbook.close()
                readable_files += 1

    with urlopen("http://127.0.0.1:9000/health", timeout=5) as response:
        health = json.loads(response.read().decode("utf-8"))["data"]

    emit(
        "runtime_configuration",
        "passed",
        python=sys.executable,
        app_env=settings.app_env,
        auth_mode=settings.auth_mode,
        database=database_name,
        demo_seed_enabled=settings.demo_seed_enabled,
        session_cookie_secure=settings.session_cookie_secure,
        persistence=health["persistence"],
    )
    emit(
        "postgres_connection",
        "passed",
        database=database_probe[0],
        role=database_probe[1],
        alembic_revision=database_probe[2],
    )
    emit(
        "persistent_state",
        "passed",
        session_count=len(sessions),
        platform_audit_count=len(audits),
        quote_count=len(quotes),
        quote_item_count=table_counts[3],
        supplier_count=table_counts[4],
        offer_count=table_counts[5],
        version_metadata_count=table_counts[6],
        ready_file_count=ready_files,
        readable_excel_count=readable_files,
    )
    emit(
        "verification",
        "passed",
        real_postgres=True,
        in_memory_fallback=False,
        external_services_called=False,
        browser_secure_cookie_login=False,
        https_prerequisite="D1.2",
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        emit("verification", "failed", error_type=type(error).__name__, message=str(error))
        raise SystemExit(1)
