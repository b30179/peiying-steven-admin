from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.core.audit import AuditRepository
from app.core.config import Settings
from app.core.login_protection import RedisLoginRateLimiter
from app.main import create_app
from app.modules.accounts.repository import InMemoryAuthRepository, PostgresAuthRepository

TEST_ORIGIN = "https://testserver"
TEST_PASSWORD = "test-only-password"


def test_0006_prechecks_conflicts_and_creates_lower_username_unique_index():
    migration = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260716_0006_p0b1_production_readiness.py"
    ).read_text(encoding="utf-8")
    assert 'down_revision = "20260716_0005"' in migration
    assert "GROUP BY lower(username)" in migration
    assert "HAVING count(*) > 1" in migration
    assert "case-insensitive username conflicts must be governed" in migration
    assert 'op.create_index("uq_users_username_lower"' in migration
    assert "platform_audit_events" in migration


def test_case_insensitive_and_concurrent_memory_user_creation_allows_one():
    repository = InMemoryAuthRepository()

    def create(username: str):
        try:
            repository.create_user(username, username, TEST_PASSWORD, {"operator"}, "admin.test")
            return "created"
        except ValueError as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(create, ["Steven.User", "steven.user"]))
    assert sorted(outcomes) == ["created", "duplicate_username"]
    assert len(repository.list_users()) == 1


def test_bootstrap_username_conflict_uses_duplicate_username():
    repository = InMemoryAuthRepository()
    repository.add_user("Initial.Admin", TEST_PASSWORD, {"operator"})
    with pytest.raises(ValueError, match="duplicate_username"):
        repository.bootstrap_admin("initial.admin", "冲突管理员", TEST_PASSWORD)


def test_postgres_unique_constraint_mapping_is_narrow():
    class Diagnostic:
        constraint_name = "uq_users_username_lower"

    class OriginalError(Exception):
        diag = Diagnostic()

    username_error = IntegrityError("insert", {}, OriginalError())
    assert PostgresAuthRepository._is_username_conflict(username_error) is True
    Diagnostic.constraint_name = "uq_user_roles_user_role"
    other_error = IntegrityError("insert", {}, OriginalError())
    assert PostgresAuthRepository._is_username_conflict(other_error) is False


def test_platform_audit_captures_request_id_and_security_rejection():
    repository = InMemoryAuthRepository()
    repository.add_user("steven", TEST_PASSWORD, {"operator"})
    audit = AuditRepository()
    settings = Settings(app_env="test", auth_mode="session", demo_seed_enabled=True)
    client = TestClient(create_app(settings, repository, audit_repository=audit), base_url=TEST_ORIGIN)
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "steven", "password": "wrong"},
        headers={"Origin": TEST_ORIGIN, "X-Request-Id": "p0b1-request-001"},
    )
    assert response.status_code == 401
    events = audit.list()
    assert any(event["action"] == "auth.login_failed" and event["request_id"] == "p0b1-request-001" for event in events)


@pytest.mark.parametrize("mode", ["", "memory"])
def test_controlled_environment_rejects_missing_or_memory_rate_limit(mode: str):
    with pytest.raises(RuntimeError, match="RATE_LIMIT_MODE"):
        Settings(
            app_env="production",
            auth_mode="session",
            demo_seed_enabled=False,
            database_url="postgresql+psycopg://service:placeholder@db/steven",
            file_storage_root="/srv/steven",
            rate_limit_mode=mode,
        ).validate()


def test_gateway_requires_trusted_proxy_and_redis_requires_adapter_config():
    with pytest.raises(RuntimeError, match="TRUSTED_PROXY_CIDRS"):
        Settings(
            app_env="staging",
            auth_mode="session",
            demo_seed_enabled=False,
            database_url="postgresql+psycopg://service:placeholder@db/steven",
            file_storage_root="/srv/steven",
            rate_limit_mode="gateway",
        ).validate()
    with pytest.raises(RuntimeError, match="REDIS_RATE_LIMIT_URL"):
        Settings(app_env="test", auth_mode="session", rate_limit_mode="redis").validate()


def test_redis_rate_limiter_contract_works_with_fake_backend():
    class FakeBackend:
        def __init__(self):
            self.failures: set[str] = set()

        def allow(self, key: str, attempts: int, window_seconds: int) -> bool:
            assert attempts == 2 and window_seconds == 30
            return key not in self.failures

        def record_failure(self, key: str, window_seconds: int) -> None:
            assert window_seconds == 30
            self.failures.add(key)

        def clear(self, key: str) -> None:
            self.failures.discard(key)

    backend = FakeBackend()
    limiter = RedisLoginRateLimiter(backend, attempts=2, window_seconds=30)
    assert limiter.allow("client:user") is True
    limiter.record_failure("client:user")
    assert limiter.allow("client:user") is False
    limiter.clear("client:user")
    assert limiter.allow("client:user") is True


def test_untrusted_forwarded_for_does_not_control_rate_limit_key():
    class CapturingLimiter:
        def __init__(self):
            self.keys: list[str] = []

        def allow(self, key: str) -> bool:
            self.keys.append(key)
            return False

        def record_failure(self, key: str) -> None:
            self.keys.append(key)

        def clear(self, key: str) -> None:
            self.keys.append(key)

    repository = InMemoryAuthRepository()
    audit = AuditRepository()
    limiter = CapturingLimiter()
    settings = Settings(app_env="test", auth_mode="session", trusted_proxy_cidrs=())
    client = TestClient(create_app(settings, repository, audit_repository=audit, login_rate_limiter=limiter), base_url=TEST_ORIGIN)
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "steven", "password": TEST_PASSWORD},
        headers={"Origin": TEST_ORIGIN, "X-Forwarded-For": "203.0.113.9"},
    )
    assert response.status_code == 429
    assert limiter.keys == ["testclient:steven"]


def test_governance_and_reserved_scan_tools_are_non_destructive_by_default():
    scripts_root = Path(__file__).resolve().parents[3] / "scripts"
    governance = (scripts_root / "govern_s2_approval_actors.py").read_text(encoding="utf-8")
    scanner = (scripts_root / "scan_s2_reserved_exports.py").read_text(encoding="utf-8")
    assert "P0B1_ACTOR_GOVERNANCE_APPROVED" in governance
    assert "VALIDATE CONSTRAINT" in governance
    assert "DELETE FROM steven_quote_approvals" not in governance
    assert "status='reserved'" in scanner
    assert "ready_candidate" in scanner and "failed_candidate" in scanner
    assert "UPDATE steven_quote_versions" not in scanner


def test_postgres_smoke_covers_concurrent_case_insensitive_user_creation():
    verifier = (Path(__file__).resolve().parents[3] / "scripts" / "verify_p0b_postgres.py").read_text(encoding="utf-8")
    assert "create_case_variant" in verifier
    assert "case_username.lower()" in verifier
    assert "duplicate_username" in verifier


def test_0010_renames_role_semantics_and_grants_dashboard_read_only():
    migration = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260717_0010_operator_role_semantics.py"
    ).read_text(encoding="utf-8")
    assert 'revision = "20260717_0010"' in migration
    assert 'down_revision = "20260717_0009"' in migration
    assert "operator role code is already used" in migration
    assert "SET code = 'operator'" in migration
    assert "'perm-dashboard-read'" in migration
    assert "'role-approver'" in migration
    assert "'role-admin'" in migration
