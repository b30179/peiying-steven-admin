from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = PROJECT_ROOT / "apps" / "api"


def result(step: str, status: str, **details: object) -> None:
    print(json.dumps({"step": step, "status": status, **details}, ensure_ascii=False))


def main() -> int:
    required = ["DATABASE_URL", "FILE_STORAGE_ROOT", "P0B_RECONCILE_ACTOR_USER_ID"]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        result("configuration", "failed", missing=missing)
        return 2
    if os.getenv("AUTH_MODE") != "session" or os.getenv("APP_ENV") not in {"development", "test", "staging"}:
        result("configuration", "failed", reason="Reconciliation requires an explicitly configured non-production session environment")
        return 2

    sys.path.insert(0, str(API_ROOT))
    from app.core.api_response import ApiError
    from app.core.config import Settings
    from app.modules.steven.quote_application import StevenQuoteApplicationService
    from app.modules.steven.quote_excel import LocalAppendOnlyQuoteStorage, QuoteExcelExporter, QuoteImportParser
    from app.modules.steven.quote_uow import PostgresQuoteUnitOfWork

    try:
        settings = Settings.from_env()
        settings.validate()
        root = Path(settings.file_storage_root).resolve()
        if not root.is_dir():
            raise RuntimeError("FILE_STORAGE_ROOT does not exist")
        engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
        actor = os.environ["P0B_RECONCILE_ACTOR_USER_ID"]
        with engine.connect() as connection:
            actor_is_admin = connection.execute(text("""
                SELECT 1 FROM users user_account
                JOIN user_roles assignment ON assignment.user_id=user_account.id
                JOIN roles role ON role.id=assignment.role_id
                WHERE user_account.id=:actor AND user_account.status='active' AND role.code='admin' AND role.status='active'
            """), {"actor": actor}).first()
            if not actor_is_admin:
                raise RuntimeError("P0B_RECONCILE_ACTOR_USER_ID must identify an active administrator")
            reservations = connection.execute(text("""
                SELECT id,quote_job_id FROM steven_quote_versions
                WHERE status='reserved' ORDER BY created_at,id
            """)).mappings().all()
        exporter = QuoteExcelExporter(root)
        application = StevenQuoteApplicationService(
            PostgresQuoteUnitOfWork(engine),
            QuoteImportParser(),
            exporter,
            LocalAppendOnlyQuoteStorage(root),
        )
        outcomes = []
        for reservation in reservations:
            try:
                version = application.reconcile_export(reservation["quote_job_id"], reservation["id"], actor)
                outcomes.append({"version_id": reservation["id"], "status": version.status})
            except ApiError as error:
                outcomes.append({"version_id": reservation["id"], "status": "failed", "code": error.code})
        result("reconcile_reserved_exports", "passed", scanned=len(reservations), outcomes=outcomes)
    except Exception as error:
        result("reconciliation", "failed", error=type(error).__name__, message=str(error))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
