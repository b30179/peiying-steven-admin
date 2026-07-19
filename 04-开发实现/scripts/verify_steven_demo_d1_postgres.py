from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from uuid import uuid4

import psycopg2
from psycopg2 import sql
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = PROJECT_ROOT / "apps" / "api"
FIXTURE_ROOT = PROJECT_ROOT / "demo-data" / "steven-d0"
FILE_ROOT = (PROJECT_ROOT / "data" / "steven-demo-d1").resolve()
DATABASE_NAME = "puiying_steven_demo"
DATABASE_ROLE = "puiying_steven_demo_app"
DATABASE_HOST = "127.0.0.1"
DATABASE_PORT = 5432
ORIGIN = "https://testserver"
EXPECTED_REVISION = "20260717_0007"
EXPECTED_TABLES = {
    "users",
    "roles",
    "permissions",
    "user_roles",
    "role_permissions",
    "auth_sessions",
    "auth_security_events",
    "platform_audit_events",
    "steven_quote_jobs",
    "steven_quote_items",
    "steven_quote_suppliers",
    "steven_quote_offer_lines",
    "steven_quote_import_batches",
    "steven_quote_approvals",
    "steven_quote_versions",
    "steven_quote_audit_events",
    "files",
    "ocr_jobs",
    "ai_jobs",
    "review_candidates",
    "steven_quote_import_candidates",
}
EXPECTED_CONSTRAINTS = {
    "uq_steven_quote_offer_lines_supplier_item",
    "fk_steven_quote_jobs_approval",
    "fk_steven_quote_import_batches_confirmed_by",
    "fk_steven_quote_approvals_submitted_by",
    "fk_steven_quote_approvals_decided_by",
}
EXPECTED_INDEXES = {
    "uq_users_username_lower",
    "uq_steven_quote_approvals_one_pending",
    "ix_platform_audit_request_time",
    "ix_review_candidates_route_status",
    "ix_steven_quote_import_candidates_job",
}
NORMAL_FIXTURES = (
    "01_supplier_a_zh_scanned",
    "02_supplier_b_mixed_numbers",
    "03_supplier_c_bilingual_table",
)


def emit(step: str, status: str, **details: object) -> None:
    print(json.dumps({"step": step, "status": status, **details}, ensure_ascii=False, default=str))


def safe_subprocess(*arguments: str, env: dict[str, str], expected_codes: set[int] | None = None) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        [sys.executable, *arguments],
        cwd=API_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode not in (expected_codes or {0}):
        output = "\n".join(part for part in (process.stdout.strip(), process.stderr.strip()) if part)
        raise RuntimeError(f"Command failed with exit code {process.returncode}: {' '.join(arguments)}\n{output[:1500]}")
    return process


def pgpass_path() -> Path:
    configured = os.getenv("PGPASSFILE", "").strip()
    if configured:
        return Path(configured)
    appdata = os.getenv("APPDATA", "").strip()
    if not appdata:
        raise RuntimeError("APPDATA is unavailable; cannot locate the approved pgpass file")
    return Path(appdata) / "postgresql" / "pgpass.conf"


def append_demo_pgpass(password: str) -> None:
    path = pgpass_path()
    if not path.is_file():
        raise RuntimeError("Approved pgpass file is missing")
    marker = f"{DATABASE_HOST}:{DATABASE_PORT}:{DATABASE_NAME}:{DATABASE_ROLE}:"
    existing = path.read_text(encoding="utf-8")
    if any(line.startswith(marker) for line in existing.splitlines()):
        return
    newline = "" if not existing or existing.endswith(("\n", "\r")) else os.linesep
    with path.open("a", encoding="utf-8", newline="") as stream:
        stream.write(f"{newline}{marker}{password}{os.linesep}")


def admin_connection():
    return psycopg2.connect(
        host=DATABASE_HOST,
        port=DATABASE_PORT,
        dbname="postgres",
        user=os.getenv("D1_ADMIN_USER", "postgres"),
        connect_timeout=5,
    )


def demo_connection():
    return psycopg2.connect(
        host=DATABASE_HOST,
        port=DATABASE_PORT,
        dbname=DATABASE_NAME,
        user=DATABASE_ROLE,
        connect_timeout=5,
    )


def prepare_isolated_database() -> None:
    generated_password: str | None = None
    connection = admin_connection()
    try:
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls
                  FROM pg_roles
                 WHERE rolname=%s
                """,
                (DATABASE_ROLE,),
            )
            role = cursor.fetchone()
            if role is None:
                generated_password = secrets.token_urlsafe(36)
                cursor.execute(
                    sql.SQL(
                        """
                        CREATE ROLE {} WITH LOGIN PASSWORD %s
                        NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
                        CONNECTION LIMIT 20
                        """
                    ).format(sql.Identifier(DATABASE_ROLE)),
                    (generated_password,),
                )
            elif any(role[index] for index in range(1, 6)):
                raise RuntimeError(f"Existing Demo role has prohibited cluster privileges: {role}")
            cursor.execute(
                "SELECT datname, pg_get_userbyid(datdba) FROM pg_database WHERE datname=%s",
                (DATABASE_NAME,),
            )
            database = cursor.fetchone()
            if database is None:
                if generated_password is None:
                    generated_password = secrets.token_urlsafe(36)
                    cursor.execute(
                        sql.SQL("ALTER ROLE {} PASSWORD %s").format(sql.Identifier(DATABASE_ROLE)),
                        (generated_password,),
                    )
                cursor.execute(
                    sql.SQL("CREATE DATABASE {} OWNER {} ENCODING 'UTF8' TEMPLATE template0").format(
                        sql.Identifier(DATABASE_NAME),
                        sql.Identifier(DATABASE_ROLE),
                    )
                )
            elif database[1] != DATABASE_ROLE:
                raise RuntimeError("Existing Demo database is not owned by the approved Demo role")
            cursor.execute(
                sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(DATABASE_NAME))
            )
            cursor.execute(
                sql.SQL("GRANT CONNECT, TEMPORARY ON DATABASE {} TO {}").format(
                    sql.Identifier(DATABASE_NAME),
                    sql.Identifier(DATABASE_ROLE),
                )
            )
    finally:
        connection.close()
    if generated_password is not None:
        append_demo_pgpass(generated_password)
    connection = demo_connection()
    try:
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
            cursor.execute(
                sql.SQL("GRANT USAGE, CREATE ON SCHEMA public TO {}").format(sql.Identifier(DATABASE_ROLE))
            )
    finally:
        connection.close()
    emit("isolated_database", "passed", database=DATABASE_NAME, role=DATABASE_ROLE, created_or_reused=True)


def database_url() -> str:
    return f"postgresql+psycopg2://{DATABASE_ROLE}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"


def application_environment(bootstrap_password: str) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "APP_ENV": "staging",
            "AUTH_MODE": "session",
            "DEMO_SEED_ENABLED": "false",
            "DATABASE_URL": database_url(),
            "FILE_STORAGE_ROOT": str(FILE_ROOT),
            "ALLOWED_ORIGINS": ORIGIN,
            "RATE_LIMIT_MODE": "gateway",
            "TRUSTED_PROXY_CIDRS": "127.0.0.1/32",
            "SESSION_COOKIE_SECURE": "true",
            "DEMO_PROFILE_ENABLED": "true",
            "OCR_ENABLED": "false",
            "AI_STRUCTURING_ENABLED": "false",
            "BOOTSTRAP_ADMIN_USERNAME": "d1.bootstrap.admin",
            "BOOTSTRAP_ADMIN_DISPLAY_NAME": "D1 首管理员（脱敏验证）",
            "BOOTSTRAP_ADMIN_PASSWORD": bootstrap_password,
        }
    )
    return environment


def migration_and_schema_smoke(environment: dict[str, str]) -> None:
    upgrade = safe_subprocess("-m", "alembic", "upgrade", "head", env=environment)
    current = safe_subprocess("-m", "alembic", "current", env=environment)
    if EXPECTED_REVISION not in current.stdout:
        raise RuntimeError(f"alembic current did not report {EXPECTED_REVISION}")

    engine = create_engine(database_url(), future=True)
    schema = inspect(engine)
    missing_tables = sorted(EXPECTED_TABLES - set(schema.get_table_names()))
    with engine.connect() as connection:
        constraints = set(connection.execute(text("SELECT conname FROM pg_constraint")).scalars())
        indexes = set(
            connection.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname=current_schema()")
            ).scalars()
        )
        lower_index = connection.execute(
            text("SELECT indexdef FROM pg_indexes WHERE indexname='uq_users_username_lower'")
        ).scalar_one_or_none()
        offer_unique = connection.execute(
            text(
                """
                SELECT pg_get_constraintdef(oid)
                  FROM pg_constraint
                 WHERE conname='uq_steven_quote_offer_lines_supplier_item'
                """
            )
        ).scalar_one_or_none()
    missing_constraints = sorted(EXPECTED_CONSTRAINTS - constraints)
    missing_indexes = sorted(EXPECTED_INDEXES - indexes)
    if missing_tables or missing_constraints or missing_indexes:
        raise RuntimeError(
            f"Schema contract mismatch: tables={missing_tables}, constraints={missing_constraints}, indexes={missing_indexes}"
        )
    if not lower_index or "lower((username)::text)" not in lower_index.lower():
        raise RuntimeError("lower(username) unique index is missing or malformed")
    if not offer_unique or "quote_supplier_id, quote_item_id" not in offer_unique:
        raise RuntimeError("Supplier/item composite unique constraint is missing or malformed")
    emit(
        "migration_schema",
        "passed",
        revision=EXPECTED_REVISION,
        table_count=len(EXPECTED_TABLES),
        upgrade_output=upgrade.stdout.strip(),
    )


def rotate_existing_demo_admin_password(password: str) -> None:
    sys.path.insert(0, str(API_ROOT))
    from app.core.passwords import hash_password
    from app.modules.accounts.repository import PostgresAuthRepository

    engine = create_engine(database_url(), future=True)
    with engine.begin() as connection:
        user = connection.execute(
            text(
                """
                SELECT u.id
                  FROM users u
                  JOIN user_roles ur ON ur.user_id=u.id
                  JOIN roles r ON r.id=ur.role_id
                 WHERE lower(u.username)=lower(:username)
                   AND r.code='admin'
                   AND u.status='active'
                 FOR UPDATE
                """
            ),
            {"username": "d1.bootstrap.admin"},
        ).mappings().one_or_none()
        if user is None:
            raise RuntimeError("Existing D1 bootstrap administrator is missing or not an active admin")
        connection.execute(
            text(
                """
                UPDATE users
                   SET password_hash=:password_hash,
                       failed_login_count=0,
                       locked_until=NULL,
                       updated_at=now()
                 WHERE id=:id
                """
            ),
            {"password_hash": hash_password(password), "id": user["id"]},
        )
        connection.execute(
            text(
                """
                UPDATE auth_sessions
                   SET revoked_at=now(),
                       revoke_reason='d1_controlled_password_rotation',
                       is_active=false
                 WHERE user_id=:id
                   AND revoked_at IS NULL
                """
            ),
            {"id": user["id"]},
        )
        PostgresAuthRepository._insert_security_event(
            connection,
            "auth.d1_bootstrap_password_rotated",
            "success",
            user["id"],
            user["id"],
            {"reason": "controlled_verification_resume", "sessions_revoked": True},
        )


def bootstrap_admin(environment: dict[str, str], password: str) -> None:
    first = safe_subprocess(
        "-m",
        "app.cli",
        "bootstrap-admin",
        env=environment,
        expected_codes={0, 3},
    )
    output = first.stdout + first.stderr
    if password in output:
        raise RuntimeError("Bootstrap output contract failed")
    resumed = first.returncode == 3
    if resumed:
        if "admin_already_exists" not in first.stderr:
            raise RuntimeError("Existing bootstrap administrator was not rejected with the expected code")
        rotate_existing_demo_admin_password(password)
    elif '"status": "created"' not in first.stdout:
        raise RuntimeError("Bootstrap output contract failed")
    duplicate = safe_subprocess(
        "-m",
        "app.cli",
        "bootstrap-admin",
        env=environment,
        expected_codes={3},
    )
    duplicate_output = duplicate.stdout + duplicate.stderr
    if password in duplicate_output or "admin_already_exists" not in duplicate.stderr:
        raise RuntimeError("Duplicate bootstrap rejection contract failed")
    emit(
        "bootstrap_admin",
        "passed",
        duplicate_rejected=True,
        password_echoed=False,
        controlled_resume=resumed,
    )


def api_data(response, expected_status: int = 200):
    if response.status_code != expected_status:
        raise RuntimeError(f"Unexpected API response {response.status_code}: {response.text[:600]}")
    return response.json()["data"]


def login(application, username: str, password: str) -> TestClient:
    client = TestClient(application, base_url=ORIGIN)
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
        headers={"Origin": ORIGIN},
    )
    if response.status_code != 200:
        raise RuntimeError(f"Login failed for {username}: {response.status_code}")
    return client


def csrf_headers(client: TestClient, settings) -> dict[str, str]:
    token = client.cookies.get(settings.csrf_cookie_name)
    if not token:
        raise RuntimeError("CSRF cookie missing")
    return {"Origin": ORIGIN, settings.csrf_header_name: token}


def create_account(admin: TestClient, settings, username: str, password: str, roles: list[str]) -> dict:
    return api_data(
        admin.post(
            "/api/v1/admin/accounts",
            json={
                "username": username,
                "display_name": f"{username}（脱敏验证）",
                "password": password,
                "roles": roles,
            },
            headers=csrf_headers(admin, settings),
        ),
        201,
    )


def load_fixture_payload(name: str) -> tuple[Path, dict]:
    truth_path = FIXTURE_ROOT / f"{name}.ground-truth.json"
    truth = json.loads(truth_path.read_text(encoding="utf-8"))
    source = next(
        path
        for path in (FIXTURE_ROOT / f"{name}.pdf", FIXTURE_ROOT / f"{name}.png")
        if path.is_file()
    )
    return source, truth["candidate"]


def add_postgres_candidate(engine, quote_id: str, actor_id: str, name: str, payload: dict, request_id: str) -> str:
    from app.modules.document_intelligence.postgres_repository import PostgresDocumentIntelligenceRepository
    from app.modules.document_intelligence.schemas import DocumentFile, EvidenceLocation, ProcessingJob, ReviewCandidate
    from app.modules.document_intelligence.storage import LocalAppendOnlyDocumentFileStorage

    source, _ = load_fixture_payload(name)
    content = source.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    storage = LocalAppendOnlyDocumentFileStorage(FILE_ROOT)
    storage_key = f"documents/{quote_id}/{uuid4()}_{source.name}"
    storage.put(storage_key, content, digest)
    with engine.begin() as connection:
        repository = PostgresDocumentIntelligenceRepository(connection)
        file_record = repository.add_file(
            DocumentFile(
                document_type="supplier_quotation",
                purpose="quotation_extraction",
                original_filename=source.name,
                storage_key=storage_key,
                mime_type="application/pdf" if source.suffix.lower() == ".pdf" else "image/png",
                size_bytes=len(content),
                sha256=digest,
                created_by=actor_id,
                request_id=request_id,
            )
        )
        ocr_job = repository.add_ocr_job(
            ProcessingJob(
                file_id=file_record.id,
                document_type="supplier_quotation",
                purpose="quotation_extraction",
                provider="mock",
                model="d0-fixture-ocr-v1",
                status="needs_review",
                request_id=request_id,
                output_json={"source": "mock", "fixture": source.name},
            )
        )
        ai_job = repository.add_ai_job(
            ProcessingJob(
                file_id=file_record.id,
                document_type="supplier_quotation",
                purpose="quotation_extraction",
                provider="mock",
                model="d0-fixture-ai-v1",
                status="needs_review",
                request_id=request_id,
                output_json={"source": "mock", "candidate": payload},
            )
        )
        candidate = repository.add_candidate(
            ReviewCandidate(
                source_file_id=file_record.id,
                ocr_job_id=ocr_job.id,
                ai_job_id=ai_job.id,
                document_type="supplier_quotation",
                purpose="quotation_extraction",
                schema_name="steven.s2.quotation",
                schema_version="1.0",
                provider="mock+mock",
                model="d0-fixture-ocr-v1+d0-fixture-ai-v1",
                status="needs_review",
                candidate_json=payload,
                warnings=["当前使用脱敏演示资料", "OCR/AI 提取结果，必须人工确认"],
                evidence=[
                    EvidenceLocation(
                        field_path="supplier_name",
                        page=1,
                        original_text="脱敏演示供应商",
                        bbox=[10, 10, 100, 25],
                        confidence=0.98,
                    )
                ],
                target_object_type="steven_quote_job",
                target_object_id=quote_id,
                request_id=request_id,
            )
        )
    return candidate.id


@contextmanager
def request_id_context(request_id: str):
    from app.core.audit_context import reset_request_id, set_request_id

    token = set_request_id(request_id)
    try:
        yield
    finally:
        reset_request_id(token)


def confirm_baseline_candidates(engine, quote_id: str, actor_id: str) -> object:
    from app.modules.steven.quote_excel import LocalAppendOnlyQuoteStorage, QuoteExcelExporter, QuoteImportParser
    from app.modules.steven.scan_import_application import PostgresScanImportUnitOfWork, StevenScanImportApplicationService

    exporter = QuoteExcelExporter(FILE_ROOT)
    application = StevenScanImportApplicationService(
        PostgresScanImportUnitOfWork(engine),
        QuoteImportParser(),
        exporter,
        LocalAppendOnlyQuoteStorage(exporter.data_root),
    )
    result = None
    for name in NORMAL_FIXTURES:
        _, payload = load_fixture_payload(name)
        request_id = f"d1-candidate-{uuid4()}"
        candidate_id = add_postgres_candidate(engine, quote_id, actor_id, name, payload, request_id)
        with request_id_context(request_id):
            result = application.confirm_scan_candidate(candidate_id, quote_id, actor_id)
    if result is None:
        raise RuntimeError("No D0 candidates were confirmed")
    return result


def forced_candidate_rollback(engine, quote_id: str, actor_id: str) -> dict[str, int]:
    from app.core.api_response import ApiError
    from app.modules.steven.postgres_quote_repository import PostgresQuoteRepository
    from app.modules.steven.quote_excel import LocalAppendOnlyQuoteStorage, QuoteExcelExporter, QuoteImportParser
    from app.modules.steven.scan_import_application import PostgresScanImportUnitOfWork, StevenScanImportApplicationService

    _, payload = load_fixture_payload(NORMAL_FIXTURES[0])
    payload = json.loads(json.dumps(payload))
    payload["supplier_code"] = "SUP-ROLLBACK"
    payload["supplier_name"] = "事务回滚供应商（脱敏）"
    request_id = f"d1-rollback-{uuid4()}"
    candidate_id = add_postgres_candidate(engine, quote_id, actor_id, NORMAL_FIXTURES[0], payload, request_id)
    with engine.connect() as connection:
        before = {
            "suppliers": connection.execute(
                text("SELECT count(*) FROM steven_quote_suppliers WHERE quote_job_id=:id"),
                {"id": quote_id},
            ).scalar_one(),
            "offers": connection.execute(
                text(
                    """
                    SELECT count(*) FROM steven_quote_offer_lines line
                    JOIN steven_quote_suppliers supplier ON supplier.id=line.quote_supplier_id
                    WHERE supplier.quote_job_id=:id
                    """
                ),
                {"id": quote_id},
            ).scalar_one(),
            "audits": connection.execute(
                text("SELECT count(*) FROM steven_quote_audit_events WHERE object_id=:id"),
                {"id": quote_id},
            ).scalar_one(),
        }

    exporter = QuoteExcelExporter(FILE_ROOT)
    application = StevenScanImportApplicationService(
        PostgresScanImportUnitOfWork(engine),
        QuoteImportParser(),
        exporter,
        LocalAppendOnlyQuoteStorage(exporter.data_root),
    )
    original = PostgresQuoteRepository.add_offer
    calls = {"count": 0}

    def fail_on_third_offer(self, *args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 3:
            raise RuntimeError("d1_forced_transaction_failure")
        return original(self, *args, **kwargs)

    PostgresQuoteRepository.add_offer = fail_on_third_offer
    try:
        with request_id_context(request_id):
            application.confirm_scan_candidate(candidate_id, quote_id, actor_id)
    except RuntimeError as error:
        if str(error) != "d1_forced_transaction_failure":
            raise
    except ApiError:
        raise
    else:
        raise RuntimeError("Forced candidate transaction failure did not fail")
    finally:
        PostgresQuoteRepository.add_offer = original

    with engine.connect() as connection:
        after = {
            "suppliers": connection.execute(
                text("SELECT count(*) FROM steven_quote_suppliers WHERE quote_job_id=:id"),
                {"id": quote_id},
            ).scalar_one(),
            "offers": connection.execute(
                text(
                    """
                    SELECT count(*) FROM steven_quote_offer_lines line
                    JOIN steven_quote_suppliers supplier ON supplier.id=line.quote_supplier_id
                    WHERE supplier.quote_job_id=:id
                    """
                ),
                {"id": quote_id},
            ).scalar_one(),
            "audits": connection.execute(
                text("SELECT count(*) FROM steven_quote_audit_events WHERE object_id=:id"),
                {"id": quote_id},
            ).scalar_one(),
            "candidate_status": connection.execute(
                text("SELECT status FROM review_candidates WHERE id=:id"),
                {"id": candidate_id},
            ).scalar_one(),
        }
    if after["candidate_status"] != "needs_review" or {key: after[key] for key in before} != before:
        raise RuntimeError(f"Candidate failure left partial writes: before={before}, after={after}")
    return before


def duplicate_offer_constraint(engine, quote_id: str, actor_id: str) -> str:
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO steven_quote_offer_lines
                        (id,quote_supplier_id,quote_item_id,unit_price,line_total,remark,status,
                         created_at,updated_at,created_by,updated_by)
                    SELECT :id,quote_supplier_id,quote_item_id,unit_price,line_total,'D1 duplicate check','active',
                           now(),now(),:actor,:actor
                      FROM steven_quote_offer_lines line
                      JOIN steven_quote_suppliers supplier ON supplier.id=line.quote_supplier_id
                     WHERE supplier.quote_job_id=:quote_id
                     LIMIT 1
                    """
                ),
                {"id": str(uuid4()), "actor": actor_id, "quote_id": quote_id},
            )
    except IntegrityError as error:
        constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
        if constraint != "uq_steven_quote_offer_lines_supplier_item":
            raise RuntimeError(f"Unexpected duplicate-offer constraint: {constraint}") from error
        return constraint
    raise RuntimeError("Database accepted a duplicate supplier/item offer")


def concurrent_case_username(application, settings, admin_username: str, admin_password: str) -> list[tuple[int, str]]:
    base = f"D1.Case-{secrets.token_hex(5)}"

    def create(username: str) -> tuple[int, str]:
        client = login(application, admin_username, admin_password)
        response = client.post(
            "/api/v1/admin/accounts",
            json={
                "username": username,
                "display_name": "D1 大小写并发唯一验证（脱敏）",
                "password": f"D1-case-{secrets.token_urlsafe(18)}",
                "roles": ["operator"],
            },
            headers=csrf_headers(client, settings),
        )
        body = response.json()
        return response.status_code, body.get("error", {}).get("code", "success")

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(create, (base, base.lower())))
    if sorted(status for status, _ in outcomes) != [201, 409]:
        raise RuntimeError(f"Concurrent case-insensitive username status mismatch: {outcomes}")
    if "duplicate_username" not in {code for _, code in outcomes}:
        raise RuntimeError(f"Concurrent username conflict was not mapped to duplicate_username: {outcomes}")
    return outcomes


def application_and_transaction_smoke(environment: dict[str, str], bootstrap_password: str) -> None:
    sys.path.insert(0, str(API_ROOT))
    from app.core.config import Settings
    from app.main import create_app

    settings = Settings.from_env()
    settings.validate()
    engine = create_engine(database_url(), pool_pre_ping=True, future=True)
    application = create_app(settings)
    admin = login(application, environment["BOOTSTRAP_ADMIN_USERNAME"], bootstrap_password)
    suffix = secrets.token_hex(5)
    passwords = {
        "steven": f"D1-steven-{secrets.token_urlsafe(18)}",
        "approver": f"D1-approver-{secrets.token_urlsafe(18)}",
        "dual": f"D1-dual-{secrets.token_urlsafe(18)}",
    }
    users = {
        "steven": create_account(admin, settings, f"d1-steven-{suffix}", passwords["steven"], ["operator"]),
        "approver": create_account(admin, settings, f"d1-approver-{suffix}", passwords["approver"], ["approver"]),
        "dual": create_account(admin, settings, f"d1-dual-{suffix}", passwords["dual"], ["operator", "approver"]),
    }
    username_outcomes = concurrent_case_username(
        application,
        settings,
        environment["BOOTSTRAP_ADMIN_USERNAME"],
        bootstrap_password,
    )

    steven = login(application, users["steven"]["username"], passwords["steven"])
    quote = api_data(
        steven.post(
            "/api/v1/steven/quotes",
            json={"subject": "D1 脱敏 OCR/AI 候选采购比价", "currency": "HKD", "is_demo": True},
            headers=csrf_headers(steven, settings),
        ),
        201,
    )
    quote_id = quote["id"]
    confirmed = confirm_baseline_candidates(engine, quote_id, users["steven"]["id"])
    ranking = confirmed.comparison.ranking
    persisted = api_data(steven.get(f"/api/v1/steven/quotes/{quote_id}"))
    supplier_by_code = {supplier["supplier_code"]: supplier for supplier in persisted["suppliers"]}
    supplier_code_by_id = {supplier["id"]: code for code, supplier in supplier_by_code.items()}
    totals = {supplier_code_by_id[entry.supplier_id]: float(entry.total) for entry in ranking}
    expected_totals = {"SUP-C": 2583.0, "SUP-A": 2605.0, "SUP-B": 2622.0}
    if totals != expected_totals:
        raise RuntimeError(f"D0/S2 totals mismatch: {totals}")
    if any(float(entry.total) != float(entry.subtotal + entry.freight + entry.tax) for entry in ranking):
        raise RuntimeError("Supplier freight/tax was not counted exactly once")
    rollback_counts = forced_candidate_rollback(engine, quote_id, users["steven"]["id"])

    non_lowest_id = supplier_by_code["SUP-A"]["id"]
    missing_reason = steven.post(
        f"/api/v1/steven/quotes/{quote_id}/recommendation",
        json={
            "recommended_supplier_id": non_lowest_id,
            "non_lowest_reason": "",
            "approval_opinion": "人工审批意见",
        },
        headers=csrf_headers(steven, settings),
    )
    missing_opinion = steven.post(
        f"/api/v1/steven/quotes/{quote_id}/recommendation",
        json={
            "recommended_supplier_id": non_lowest_id,
            "non_lowest_reason": "交付期更符合演示要求",
            "approval_opinion": "",
        },
        headers=csrf_headers(steven, settings),
    )
    missing_reason_error = missing_reason.json().get("error", {})
    missing_opinion_error = missing_opinion.json().get("error", {})
    if (
        missing_reason.status_code != 422
        or missing_opinion.status_code != 422
        or missing_reason_error.get("code") != "non_lowest_justification_required"
        or missing_opinion_error.get("code") != "non_lowest_justification_required"
        or missing_reason_error.get("details", {}).get("non_lowest_reason_required") is not True
        or missing_reason_error.get("details", {}).get("approval_opinion_required") is not True
        or missing_opinion_error.get("details", {}).get("non_lowest_reason_required") is not True
        or missing_opinion_error.get("details", {}).get("approval_opinion_required") is not True
    ):
        raise RuntimeError(
            f"Non-lowest recommendation validation failed: {missing_reason.text}, {missing_opinion.text}"
        )
    api_data(
        steven.post(
            f"/api/v1/steven/quotes/{quote_id}/recommendation",
            json={
                "recommended_supplier_id": non_lowest_id,
                "non_lowest_reason": "交付期更符合脱敏演示要求",
                "approval_opinion": "人工确认非最低价选择，仅用于脱敏演示",
            },
            headers=csrf_headers(steven, settings),
        )
    )
    api_data(
        steven.post(
            f"/api/v1/steven/quotes/{quote_id}/submit-approval",
            headers=csrf_headers(steven, settings),
        )
    )
    approver = login(application, users["approver"]["username"], passwords["approver"])
    api_data(
        approver.post(
            f"/api/v1/steven/quotes/{quote_id}/approve",
            json={"opinion": "D1 脱敏人工审批通过"},
            headers=csrf_headers(approver, settings),
        )
    )

    dual = login(application, users["dual"]["username"], passwords["dual"])
    self_quote = api_data(
        dual.post(
            "/api/v1/steven/quotes",
            json={"subject": "D1 自审阻断（脱敏）", "currency": "HKD", "is_demo": True},
            headers=csrf_headers(dual, settings),
        ),
        201,
    )
    self_confirmed = confirm_baseline_candidates(engine, self_quote["id"], users["dual"]["id"])
    lowest_id = self_confirmed.comparison.lowest_supplier_id
    api_data(
        dual.post(
            f"/api/v1/steven/quotes/{self_quote['id']}/recommendation",
            json={
                "recommended_supplier_id": lowest_id,
                "non_lowest_reason": "",
                "approval_opinion": "",
            },
            headers=csrf_headers(dual, settings),
        )
    )
    api_data(
        dual.post(
            f"/api/v1/steven/quotes/{self_quote['id']}/submit-approval",
            headers=csrf_headers(dual, settings),
        )
    )
    self_approval = dual.post(
        f"/api/v1/steven/quotes/{self_quote['id']}/approve",
        json={"opinion": "不得成功"},
        headers=csrf_headers(dual, settings),
    )
    if self_approval.status_code != 403 or self_approval.json()["error"]["code"] != "self_approval_forbidden":
        raise RuntimeError("Submitter self-approval was not rejected")

    exports = []
    for _ in range(3):
        exports.append(
            api_data(
                steven.post(
                    f"/api/v1/steven/quotes/{quote_id}/export",
                    headers=csrf_headers(steven, settings),
                )
            )
        )
    version_numbers = [entry["version"]["version_number"] for entry in exports]
    if version_numbers != [1, 2, 3]:
        raise RuntimeError(f"Export versions are not continuous: {version_numbers}")

    duplicate_constraint = duplicate_offer_constraint(engine, quote_id, users["steven"]["id"])

    restarted_application = create_app(settings)
    session_cookie = steven.cookies.get(settings.session_cookie_name)
    restarted_session = TestClient(restarted_application, base_url=ORIGIN)
    restarted_session.cookies.set(settings.session_cookie_name, session_cookie)
    if restarted_session.get("/api/v1/auth/me").status_code != 200:
        raise RuntimeError("Existing Session did not survive application restart")
    restarted_steven = login(restarted_application, users["steven"]["username"], passwords["steven"])
    restarted_quote = api_data(restarted_steven.get(f"/api/v1/steven/quotes/{quote_id}"))
    if (
        len(restarted_quote["items"]),
        len(restarted_quote["suppliers"]),
        len(restarted_quote["offer_lines"]),
    ) != (5, 3, 15):
        raise RuntimeError("Quote data did not survive application restart")
    versions = api_data(restarted_steven.get(f"/api/v1/steven/quotes/{quote_id}/versions"))
    if [entry["version_number"] for entry in versions] != [1, 2, 3]:
        raise RuntimeError("Export version metadata did not survive restart")
    for version in versions:
        path = (FILE_ROOT / version["storage_key"]).resolve()
        if FILE_ROOT not in path.parents or not path.is_file():
            raise RuntimeError("Export file is missing or escaped the controlled D1 storage root")
        load_workbook(path, read_only=True).close()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != version["sha256"] or path.stat().st_size != version["size_bytes"]:
            raise RuntimeError("Export hash or size metadata mismatch")
    quote_audits = api_data(restarted_steven.get(f"/api/v1/steven/quotes/{quote_id}/audit-events"))
    if not {"quote.scan_candidate_confirm", "quote.recommend", "quote.submit", "quote.approve", "quote.export"}.issubset(
        {event["action"] for event in quote_audits}
    ):
        raise RuntimeError("Persistent quote audit is incomplete after restart")
    restarted_admin = login(
        restarted_application,
        environment["BOOTSTRAP_ADMIN_USERNAME"],
        bootstrap_password,
    )
    platform_audits = api_data(restarted_admin.get("/api/v1/audit/events"))
    if not any(event["action"] == "auth.login_succeeded" for event in platform_audits):
        raise RuntimeError("Persistent platform audit is unavailable after restart")
    with engine.connect() as connection:
        session_count = connection.execute(text("SELECT count(*) FROM auth_sessions")).scalar_one()
        candidate_links = connection.execute(
            text("SELECT count(*) FROM steven_quote_import_candidates WHERE quote_job_id=:id"),
            {"id": quote_id},
        ).scalar_one()
    if session_count < 1 or candidate_links != 3:
        raise RuntimeError("Session or candidate-link persistence check failed")

    emit(
        "postgres_application_closure",
        "passed",
        quote_id=quote_id,
        item_count=5,
        supplier_count=3,
        offer_count=15,
        totals=totals,
        freight_tax_counted_once=True,
        non_lowest_double_confirmation=True,
        self_approval_rejected=True,
        username_concurrency=username_outcomes,
        duplicate_offer_constraint=duplicate_constraint,
        candidate_failure_rollback=rollback_counts,
        export_versions=version_numbers,
        restart_session_recovered=True,
        restart_audit_recovered=True,
        candidate_links=candidate_links,
    )


def least_privilege_smoke() -> bool:
    with admin_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls
                  FROM pg_roles
                 WHERE rolname=%s
                """,
                (DATABASE_ROLE,),
            )
            role = cursor.fetchone()
            cursor.execute(
                """
                SELECT pg_get_userbyid(datdba), has_database_privilege(%s, %s, 'CONNECT')
                  FROM pg_database
                 WHERE datname=%s
                """,
                (DATABASE_ROLE, DATABASE_NAME, DATABASE_NAME),
            )
            database = cursor.fetchone()
            cursor.execute(
                """
                SELECT database, address, auth_method, error
                  FROM pg_hba_file_rules
                 WHERE type='host'
                   AND user_name @> ARRAY[%s]
                 ORDER BY line_number
                """,
                (DATABASE_ROLE,),
            )
            role_hba_rules = cursor.fetchall()
    if role is None or any(role[index] for index in range(1, 6)):
        raise RuntimeError(f"Demo role has prohibited cluster privileges: {role}")
    if database != (DATABASE_ROLE, True):
        raise RuntimeError(f"Demo database ownership/connect contract failed: {database}")
    emit(
        "least_privilege",
        "passed",
        role=DATABASE_ROLE,
        target_database=DATABASE_NAME,
        superuser=False,
        create_database=False,
        create_role=False,
        replication=False,
        bypass_rls=False,
        note="No non-Demo database was enumerated or modified",
    )
    expected_hba_rules = [
        ([DATABASE_NAME], "127.0.0.1", "scram-sha-256", None),
        ([DATABASE_NAME], "::1", "scram-sha-256", None),
        (["all"], "127.0.0.1", "reject", None),
        (["all"], "::1", "reject", None),
    ]
    if role_hba_rules != expected_hba_rules:
        raise RuntimeError(f"Demo-role pg_hba isolation rules mismatch: {role_hba_rules}")
    with demo_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            if cursor.fetchone()[0] != DATABASE_NAME:
                raise RuntimeError("Demo role did not connect to the approved Demo database")
    rejected_probe_database = "postgres"
    try:
        rejected_connection = psycopg2.connect(
            host=DATABASE_HOST,
            port=DATABASE_PORT,
            dbname=rejected_probe_database,
            user=DATABASE_ROLE,
            connect_timeout=5,
        )
    except (psycopg2.OperationalError, UnicodeDecodeError):
        # PostgreSQL Windows localized fatal messages can be non-UTF-8;
        # either exception still means authentication rejected before a session.
        non_target_connection_rejected = True
    else:
        rejected_connection.close()
        raise RuntimeError("Demo role unexpectedly connected to the non-Demo aggregate isolation probe")
    emit(
        "database_connect_isolation",
        "passed",
        target_database=DATABASE_NAME,
        non_target_database_names_enumerated=False,
        non_target_tables_or_data_read_or_written=False,
        aggregate_non_target_connection_probe_count=1,
        aggregate_non_target_connection_rejected_count=1 if non_target_connection_rejected else 0,
        database_acl_public_connect_may_remain=True,
        effective_localhost_hba_deny_all_non_target=True,
        demo_target_connection_passed=True,
        blocker=None,
    )
    return True


def validate_clean_file_root() -> None:
    FILE_ROOT.mkdir(parents=True, exist_ok=True)
    preserved_entries = sum(1 for _ in FILE_ROOT.rglob("*"))
    emit(
        "file_root",
        "passed",
        path=str(FILE_ROOT),
        preserved_existing_entries=preserved_entries,
        deleted_entries=0,
    )


def main() -> int:
    bootstrap_password = f"D1-bootstrap-{secrets.token_urlsafe(24)}"
    try:
        validate_clean_file_root()
        prepare_isolated_database()
        database_connect_isolated = least_privilege_smoke()
        environment = application_environment(bootstrap_password)
        os.environ.update(environment)
        migration_and_schema_smoke(environment)
        bootstrap_admin(environment, bootstrap_password)
        application_and_transaction_smoke(environment, bootstrap_password)
    except Exception as error:
        emit(
            "verification",
            "failed",
            error=type(error).__name__,
            message=str(error).replace(bootstrap_password, "[REDACTED]"),
        )
        return 1
    if not database_connect_isolated:
        emit(
            "verification",
            "blocked",
            scope="independent Demo empty-database PostgreSQL closure",
            production_ready=False,
            external_services_called=False,
            completed_application_closure=True,
            blocker="database_connect_isolation",
        )
        return 2
    emit(
        "verification",
        "passed",
        scope="independent Demo empty-database PostgreSQL closure",
        production_ready=False,
        external_services_called=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
