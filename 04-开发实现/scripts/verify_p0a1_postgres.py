from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = PROJECT_ROOT / "apps" / "api"
EXPECTED_TABLES = {
    "users",
    "roles",
    "permissions",
    "user_roles",
    "role_permissions",
    "auth_sessions",
    "auth_security_events",
}
EXPECTED_UNIQUES = {
    "users": {"uq_users_username", "uq_users_email"},
    "auth_sessions": {"uq_auth_sessions_token_hash"},
    "user_roles": {"uq_user_roles_user_role"},
    "role_permissions": {"uq_role_permissions_role_permission"},
}
ORIGIN = "https://testserver"


def result(step: str, status: str, **details: object) -> None:
    print(json.dumps({"step": step, "status": status, **details}, ensure_ascii=False))


def run_api_command(*arguments: str, expected_codes: set[int] | None = None) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        [sys.executable, *arguments],
        cwd=API_ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode not in (expected_codes or {0}):
        raise RuntimeError(f"Command failed with exit code {process.returncode}: {' '.join(arguments)}")
    return process


def prepare_empty_database(admin_url: str, database_url: str) -> None:
    try:
        import psycopg
    except ModuleNotFoundError as error:
        raise RuntimeError("PostgreSQL driver is unavailable; use the approved project environment with requirements.txt installed") from error
    target = make_url(database_url)
    database_name = target.database or ""
    if not re.fullmatch(r"puiying_steven_p0a1_smoke[_a-zA-Z0-9-]*", database_name):
        raise RuntimeError("Target database name must start with puiying_steven_p0a1_smoke")
    admin = make_url(admin_url)
    if admin.database == database_name:
        raise RuntimeError("Administrator connection must target a different maintenance database")
    connection_kwargs = {
        "host": admin.host,
        "port": admin.port or 5432,
        "dbname": admin.database or "postgres",
        "user": admin.username,
        "password": admin.password,
    }
    with psycopg.connect(**connection_kwargs, autocommit=True) as connection:
        exists = connection.execute("SELECT 1 FROM pg_database WHERE datname=%s", (database_name,)).fetchone()
        if exists:
            if os.getenv("P0A1_ALLOW_RECREATE", "").strip().lower() != "true":
                raise RuntimeError("Smoke database already exists; set P0A1_ALLOW_RECREATE=true for the dedicated smoke database only")
            connection.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s AND pid<>pg_backend_pid()", (database_name,))
            connection.execute(f'DROP DATABASE "{database_name}"')
        connection.execute(f'CREATE DATABASE "{database_name}"')
    result("create_empty_database", "passed", database=database_name)


def migration_and_schema_smoke(database_url: str) -> None:
    upgrade = run_api_command("-m", "alembic", "upgrade", "head")
    result("alembic_upgrade_head", "passed", output=upgrade.stdout.strip())
    current = run_api_command("-m", "alembic", "current")
    if "20260716_0004" not in current.stdout:
        raise RuntimeError("alembic current did not report 20260716_0004")
    result("alembic_current", "passed", revision="20260716_0004")

    engine = create_engine(database_url, future=True)
    schema = inspect(engine)
    missing_tables = sorted(EXPECTED_TABLES - set(schema.get_table_names()))
    if missing_tables:
        raise RuntimeError(f"Missing tables: {missing_tables}")
    for table_name, expected_names in EXPECTED_UNIQUES.items():
        actual_names = {item["name"] for item in schema.get_unique_constraints(table_name)}
        missing_names = expected_names - actual_names
        if missing_names:
            raise RuntimeError(f"Missing unique constraints on {table_name}: {sorted(missing_names)}")
    with engine.connect() as connection:
        role_count = connection.execute(text("SELECT count(*) FROM roles")).scalar_one()
        permission_count = connection.execute(text("SELECT count(*) FROM permissions")).scalar_one()
    if role_count != 3 or permission_count != 13:
        raise RuntimeError("Seeded RBAC rows do not match the approved P0-A matrix")
    result("schema_constraints", "passed", tables=len(EXPECTED_TABLES), roles=role_count, permissions=permission_count)


def bootstrap_smoke(password: str) -> None:
    first = run_api_command("-m", "app.cli", "bootstrap-admin")
    combined = first.stdout + first.stderr
    if password in combined or '"status": "created"' not in first.stdout:
        raise RuntimeError("Bootstrap output contract failed")
    duplicate = run_api_command("-m", "app.cli", "bootstrap-admin", expected_codes={3})
    duplicate_output = duplicate.stdout + duplicate.stderr
    if password in duplicate_output or "admin_already_exists" not in duplicate.stderr:
        raise RuntimeError("Duplicate bootstrap rejection contract failed")
    result("bootstrap_admin", "passed", duplicate_rejected=True, password_echoed=False)


def authentication_smoke() -> None:
    sys.path.insert(0, str(API_ROOT))
    from app.core.config import Settings
    from app.main import create_app

    settings = Settings.from_env()
    application = create_app(settings)
    admin_client = TestClient(application, base_url=ORIGIN)
    login = admin_client.post(
        "/api/v1/auth/login",
        json={"username": os.environ["BOOTSTRAP_ADMIN_USERNAME"], "password": os.environ["BOOTSTRAP_ADMIN_PASSWORD"]},
        headers={"Origin": ORIGIN},
    )
    if login.status_code != 200:
        raise RuntimeError("Administrator login failed")
    csrf_token = admin_client.cookies.get(settings.csrf_cookie_name)
    if not csrf_token or settings.session_cookie_name not in admin_client.cookies:
        raise RuntimeError("Session or CSRF cookie missing")
    csrf_headers = {"Origin": ORIGIN, settings.csrf_header_name: csrf_token}
    missing_csrf = admin_client.post(
        "/api/v1/admin/accounts",
        json={"username": "csrf-rejected", "display_name": "CSRF 拒绝测试", "password": "not-used-password", "roles": ["operator"]},
        headers={"Origin": ORIGIN},
    )
    if missing_csrf.status_code != 403:
        raise RuntimeError("Missing CSRF request was not rejected")

    test_password = "P0A1-smoke-" + os.urandom(12).hex()
    created = admin_client.post(
        "/api/v1/admin/accounts",
        json={"username": "p0a1-smoke-steven", "display_name": "Steven（脱敏空库验证）", "password": test_password, "roles": ["operator"]},
        headers=csrf_headers,
    )
    if created.status_code != 201:
        raise RuntimeError("CSRF-protected account creation failed")
    user_id = created.json()["data"]["id"]
    steven_client = TestClient(application, base_url=ORIGIN)
    steven_login = steven_client.post(
        "/api/v1/auth/login",
        json={"username": "p0a1-smoke-steven", "password": test_password},
        headers={"Origin": ORIGIN},
    )
    if steven_login.status_code != 200 or steven_client.get("/api/v1/steven/dashboard").status_code != 200:
        raise RuntimeError("Steven RBAC smoke failed")
    role_change = admin_client.put(
        f"/api/v1/admin/accounts/{user_id}/roles",
        json={"roles": ["approver"]},
        headers=csrf_headers,
    )
    if role_change.status_code != 200 or steven_client.get("/api/v1/auth/me").status_code != 401:
        raise RuntimeError("Role change did not revoke the active Session")
    forged = admin_client.get("/api/v1/audit/events", headers={"X-Role": "admin"})
    if forged.status_code != 400 or forged.json()["error"]["code"] != "legacy_identity_headers_forbidden":
        raise RuntimeError("Legacy identity header was not rejected")
    result("login_cookie_rbac_csrf", "passed", role_change_revoked_session=True, legacy_header_rejected=True)


def main() -> int:
    required = ["P0A1_ADMIN_DATABASE_URL", "DATABASE_URL", "BOOTSTRAP_ADMIN_USERNAME", "BOOTSTRAP_ADMIN_DISPLAY_NAME", "BOOTSTRAP_ADMIN_PASSWORD"]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        result("configuration", "failed", missing=missing)
        return 2
    if os.getenv("APP_ENV") not in {"development", "test"} or os.getenv("AUTH_MODE") != "session" or os.getenv("DEMO_SEED_ENABLED", "").lower() != "false":
        result("configuration", "failed", reason="APP_ENV must be development/test, AUTH_MODE=session, DEMO_SEED_ENABLED=false")
        return 2
    try:
        prepare_empty_database(os.environ["P0A1_ADMIN_DATABASE_URL"], os.environ["DATABASE_URL"])
        migration_and_schema_smoke(os.environ["DATABASE_URL"])
        bootstrap_smoke(os.environ["BOOTSTRAP_ADMIN_PASSWORD"])
        authentication_smoke()
    except Exception as error:
        result("verification", "failed", error=type(error).__name__, message=str(error))
        return 1
    result("verification", "passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
