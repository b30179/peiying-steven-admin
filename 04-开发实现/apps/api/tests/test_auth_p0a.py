from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import cli
from app.core.config import Settings
from app.main import create_app
from app.modules.accounts.repository import InMemoryAuthRepository

TEST_PASSWORD = "test-only-password"
TEST_ORIGIN = "https://testserver"


class PersistentAuditStub:
    def append(self, **values):
        return values

    def list(self):
        return []

    def list_for_object(self, object_id: str):
        del object_id
        return []


def session_app(*users: tuple[str, set[str]], login_max_failures: int = 5):
    repository = InMemoryAuthRepository()
    records = {}
    for username, roles in users:
        records[username] = repository.add_user(username, TEST_PASSWORD, roles, display_name=f"{username}（脱敏测试）", user_id=f"user-{username}")
    settings = Settings(app_env="test", auth_mode="session", demo_seed_enabled=True, database_url="", file_storage_root="./data/test", login_max_failures=login_max_failures)
    return create_app(settings, repository), repository, records


def login(client: TestClient, username: str, password: str = TEST_PASSWORD, headers: dict[str, str] | None = None):
    request_headers = {"Origin": TEST_ORIGIN, **(headers or {})}
    return client.post("/api/v1/auth/login", json={"username": username, "password": password}, headers=request_headers)


def csrf_headers(client: TestClient, origin: str = TEST_ORIGIN) -> dict[str, str]:
    return {"Origin": origin, "X-CSRF-Token": client.cookies.get("__Host-puiying_csrf")}


def secured_write(client: TestClient, method: str, path: str, **kwargs):
    headers = {**csrf_headers(client), **kwargs.pop("headers", {})}
    return client.request(method, path, headers=headers, **kwargs)


def test_unauthenticated_invalid_expired_and_revoked_sessions_return_401():
    application, repository, _ = session_app(("steven", {"operator"}))
    client = TestClient(application, base_url="https://testserver")
    assert client.get("/api/v1/steven/dashboard").status_code == 401
    client.cookies.set("__Host-puiying_session", "invalid-token")
    assert client.get("/api/v1/steven/dashboard").status_code == 401
    client.cookies.clear()
    assert login(client, "steven").status_code == 200
    session_id = repository.list_sessions()[0]["id"]
    repository.expire_session(session_id)
    assert client.get("/api/v1/steven/dashboard").status_code == 401
    client.cookies.clear()
    assert login(client, "steven").status_code == 200
    active_session = repository.list_sessions()[-1]
    assert repository.revoke_session(active_session["id"], "test_revoke") is True
    assert client.get("/api/v1/steven/dashboard").status_code == 401


def test_login_cookie_security_logout_and_me():
    application, _, _ = session_app(("steven", {"operator"}))
    client = TestClient(application, base_url="https://testserver")
    response = login(client, "steven")
    assert response.status_code == 200
    set_cookie = response.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "secure" in set_cookie
    assert "samesite=lax" in set_cookie
    assert response.json()["data"]["roles"] == ["operator"]
    assert response.json()["data"]["display_name"] == "steven（脱敏测试）"
    me_response = client.get("/api/v1/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["data"]["display_name"] == "steven（脱敏测试）"
    assert secured_write(client, "POST", "/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


def test_spoofed_identity_headers_never_change_session_permissions():
    application, repository, _ = session_app(("steven", {"operator"}))
    client = TestClient(application, base_url="https://testserver")
    assert login(client, "steven").status_code == 200
    response = client.get("/api/v1/audit/events", headers={"X-Role": "admin", "X-Actor": "forged-admin"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "legacy_identity_headers_forbidden"
    assert client.get("/api/v1/audit/events").status_code == 403
    assert any(
        event["event_type"] == "auth.authorization_rejected"
        and "audit:logs:read_all" in event["details"]["missing_permissions"]
        for event in repository.list_security_events()
    )


@pytest.mark.parametrize("header_name", ["X-Role", "X-Actor", "X-Acting-Role", "X-Acting-Actor"])
def test_all_legacy_identity_headers_are_rejected_on_login_and_business_api(header_name: str):
    application, _, _ = session_app(("steven", {"operator"}))
    client = TestClient(application, base_url=TEST_ORIGIN)
    login_response = login(client, "steven", headers={header_name: "forged"})
    assert login_response.status_code == 400
    assert login_response.json()["error"]["code"] == "legacy_identity_headers_forbidden"
    assert login(client, "steven").status_code == 200
    business_response = client.get("/api/v1/steven/quotes", headers={header_name: "forged"})
    assert business_response.status_code == 400
    assert business_response.json()["error"]["code"] == "legacy_identity_headers_forbidden"


def test_csrf_cookie_header_and_origin_are_required_for_session_writes():
    application, repository, _ = session_app(("steven", {"operator"}))
    client = TestClient(application, base_url=TEST_ORIGIN)
    assert login(client, "steven").status_code == 200
    path = "/api/v1/steven/quotes"
    payload = {"subject": "P0-A.1 脱敏测试", "currency": "HKD"}

    missing_token = client.post(path, json=payload, headers={"Origin": TEST_ORIGIN})
    assert missing_token.status_code == 403
    assert missing_token.json()["error"]["code"] == "csrf_validation_failed"

    wrong_token = client.post(path, json=payload, headers={"Origin": TEST_ORIGIN, "X-CSRF-Token": "wrong-token"})
    assert wrong_token.status_code == 403
    assert wrong_token.json()["error"]["code"] == "csrf_validation_failed"

    invalid_origin = client.post(path, json=payload, headers=csrf_headers(client, "https://evil.example"))
    assert invalid_origin.status_code == 403
    assert invalid_origin.json()["error"]["code"] == "origin_not_allowed"

    no_session = TestClient(application, base_url=TEST_ORIGIN)
    no_session.cookies.set("__Host-puiying_csrf", "csrf-only")
    missing_session = no_session.post(path, json=payload, headers={"Origin": TEST_ORIGIN, "X-CSRF-Token": "csrf-only"})
    assert missing_session.status_code == 403
    assert missing_session.json()["error"]["code"] == "csrf_validation_failed"

    success = secured_write(client, "POST", path, json=payload)
    assert success.status_code == 201
    rejection_codes = {
        event["details"]["code"]
        for event in repository.list_security_events()
        if event["event_type"] == "auth.request_rejected"
    }
    assert {"csrf_validation_failed", "origin_not_allowed"} <= rejection_codes


def test_missing_and_invalid_sessions_create_traceable_security_events():
    application, repository, _ = session_app(("steven", {"operator"}))
    client = TestClient(application, base_url=TEST_ORIGIN)
    assert client.get("/api/v1/steven/dashboard").status_code == 401
    client.cookies.set("__Host-puiying_session", "invalid-token")
    assert client.get("/api/v1/steven/dashboard").status_code == 401
    reasons = {
        event["details"]["reason"]
        for event in repository.list_security_events()
        if event["event_type"] == "auth.session_rejected"
    }
    assert reasons == {"missing_session", "invalid_expired_or_revoked"}


def test_login_origin_is_required_and_referer_can_supply_allowed_origin():
    application, _, _ = session_app(("steven", {"operator"}))
    client = TestClient(application, base_url=TEST_ORIGIN)
    missing_origin = client.post("/api/v1/auth/login", json={"username": "steven", "password": TEST_PASSWORD})
    assert missing_origin.status_code == 403
    assert missing_origin.json()["error"]["code"] == "origin_not_allowed"
    allowed_referer = client.post(
        "/api/v1/auth/login",
        json={"username": "steven", "password": TEST_PASSWORD},
        headers={"Referer": f"{TEST_ORIGIN}/login"},
    )
    assert allowed_referer.status_code == 200


def test_mock_permission_matrix_for_steven_approver_and_admin():
    steven = TestClient(create_app(Settings(app_env="test", auth_mode="mock", demo_seed_enabled=True, mock_identity="steven"), InMemoryAuthRepository()))
    assert steven.get("/api/v1/steven/dashboard").status_code == 200
    assert steven.get("/api/v1/steven/quotes").status_code == 200
    assert steven.get("/api/v1/audit/events").status_code == 403
    assert steven.post("/api/v1/steven/quotes/demo-quote-hkd-2026/approve", json={"opinion": "不应获准"}).status_code == 403

    approver = TestClient(create_app(Settings(app_env="test", auth_mode="mock", demo_seed_enabled=True, mock_identity="approver"), InMemoryAuthRepository()))
    assert approver.get("/api/v1/steven/dashboard").status_code == 200
    assert approver.get("/api/v1/steven/quotes/demo-quote-hkd-2026").status_code == 200
    assert approver.post("/api/v1/steven/quotes", json={"subject": "禁止修改", "currency": "HKD"}).status_code == 403
    assert approver.get("/api/v1/audit/events").status_code == 403

    admin = TestClient(create_app(Settings(app_env="test", auth_mode="mock", demo_seed_enabled=True, mock_identity="admin"), InMemoryAuthRepository()))
    assert admin.get("/api/v1/admin/accounts").status_code == 200
    assert admin.get("/api/v1/admin/roles").status_code == 200
    assert admin.get("/api/v1/admin/sessions").status_code == 200
    assert admin.get("/api/v1/audit/events").status_code == 200
    assert admin.get("/api/v1/steven/dashboard").status_code == 200
    assert admin.get("/api/v1/steven/quotes").status_code == 403
    assert admin.post("/api/v1/steven/quotes/demo-quote-hkd-2026/approve", json={"opinion": "管理员默认不得审批"}).status_code == 403


def test_dual_role_submitter_cannot_self_approve_but_other_approver_can():
    application, _, _ = session_app(("dual", {"operator", "approver"}), ("approver", {"approver"}))
    client = TestClient(application, base_url="https://testserver")
    assert login(client, "dual").status_code == 200
    quote_id = "demo-quote-hkd-2026"
    recommendation = secured_write(client, "POST", f"/api/v1/steven/quotes/{quote_id}/recommendation", json={"recommended_supplier_id": "demo-supplier-3", "non_lowest_reason": "", "approval_opinion": ""})
    assert recommendation.status_code == 200
    assert secured_write(client, "POST", f"/api/v1/steven/quotes/{quote_id}/submit-approval").status_code == 200
    self_approval = secured_write(client, "POST", f"/api/v1/steven/quotes/{quote_id}/approve", json={"opinion": "禁止自审"})
    assert self_approval.status_code == 403
    assert self_approval.json()["error"]["code"] == "self_approval_forbidden"
    assert secured_write(client, "POST", "/api/v1/auth/logout").status_code == 200
    assert login(client, "approver").status_code == 200
    assert secured_write(client, "POST", f"/api/v1/steven/quotes/{quote_id}/approve", json={"opinion": "已由独立审批人核对"}).status_code == 200


def test_environment_startup_guards():
    with pytest.raises(RuntimeError, match="AUTH_MODE=mock"):
        create_app(Settings(app_env="production", auth_mode="mock", demo_seed_enabled=False), InMemoryAuthRepository())
    with pytest.raises(RuntimeError, match="AUTH_MODE=mock"):
        create_app(Settings(app_env="staging", auth_mode="mock", demo_seed_enabled=False), InMemoryAuthRepository())
    with pytest.raises(RuntimeError, match="DEMO_SEED_ENABLED"):
        create_app(Settings(app_env="production", auth_mode="session", demo_seed_enabled=True, database_url="postgresql+psycopg://placeholder:placeholder@db/puiying_steven_production"), InMemoryAuthRepository())


def test_production_session_mode_can_start_with_injected_repository_and_no_demo_seed():
    settings = Settings(
        app_env="production",
        auth_mode="session",
        demo_seed_enabled=False,
        database_url="postgresql+psycopg://service:secret-placeholder@db/puiying_steven_production",
        file_storage_root="/mnt/nas/steven",
        rate_limit_mode="gateway",
        trusted_proxy_cidrs=("10.0.0.0/8",),
    )
    application = create_app(settings, InMemoryAuthRepository(), audit_repository=PersistentAuditStub())
    response = TestClient(application, base_url="https://testserver").get("/health")
    assert response.status_code == 200
    assert response.json()["data"]["demo_seed_enabled"] is False



def test_admin_account_role_and_session_management():
    application, _, _ = session_app(("admin", {"admin"}))
    admin_client = TestClient(application, base_url="https://testserver")
    user_client = TestClient(application, base_url="https://testserver")
    assert login(admin_client, "admin").status_code == 200
    created = secured_write(admin_client, "POST", "/api/v1/admin/accounts", json={"username": "new-steven", "display_name": "新 Steven（脱敏测试）", "password": TEST_PASSWORD, "roles": ["operator"]})
    assert created.status_code == 201
    user_id = created.json()["data"]["id"]
    assert login(user_client, "new-steven").status_code == 200
    changed = secured_write(admin_client, "PUT", f"/api/v1/admin/accounts/{user_id}/roles", json={"roles": ["approver"]})
    assert changed.status_code == 200
    assert changed.json()["data"]["roles"] == ["approver"]
    assert user_client.get("/api/v1/auth/me").status_code == 401
    assert secured_write(admin_client, "POST", f"/api/v1/admin/accounts/{user_id}/disable").status_code == 200
    accounts = admin_client.get("/api/v1/admin/accounts").json()["data"]
    assert next(account for account in accounts if account["id"] == user_id)["status"] == "disabled"


def test_failed_login_count_lockout_and_successful_login_reset():
    application, repository, _ = session_app(("steven", {"operator"}), login_max_failures=3)
    client = TestClient(application, base_url=TEST_ORIGIN)
    assert login(client, "steven", "wrong-password").status_code == 401
    assert repository.list_users()[0]["failed_login_count"] == 1
    assert login(client, "steven").status_code == 200
    reset_account = repository.list_users()[0]
    assert reset_account["failed_login_count"] == 0
    assert reset_account["locked_until"] is None
    assert reset_account["last_login_at"] is not None

    client.cookies.clear()
    for _ in range(3):
        assert login(client, "steven", "wrong-password").status_code == 401
    locked_account = repository.list_users()[0]
    assert locked_account["failed_login_count"] == 3
    assert locked_account["locked_until"] is not None
    assert login(client, "steven").status_code == 401
    outcomes = [event["event_type"] for event in repository.list_security_events()]
    assert "auth.login_failed" in outcomes
    assert "auth.login_succeeded" in outcomes


def test_local_login_rate_limit_is_audited():
    repository = InMemoryAuthRepository()
    repository.add_user("steven", TEST_PASSWORD, {"operator"}, display_name="Steven（脱敏测试）")
    settings = Settings(
        app_env="test",
        auth_mode="session",
        demo_seed_enabled=True,
        database_url="",
        file_storage_root="./data/test",
        login_rate_limit_attempts=2,
    )
    client = TestClient(create_app(settings, repository), base_url=TEST_ORIGIN)
    assert login(client, "steven", "wrong-password").status_code == 401
    assert login(client, "steven", "wrong-password").status_code == 401
    assert login(client, "steven", "wrong-password").status_code == 429
    assert any(event["event_type"] == "auth.login_rate_limited" for event in repository.list_security_events())


def test_bootstrap_admin_is_one_time_audited_and_never_prints_password(monkeypatch, capsys):
    repository = InMemoryAuthRepository()
    settings = Settings(app_env="test", auth_mode="session", demo_seed_enabled=False, database_url="postgresql+psycopg://placeholder", file_storage_root="./data/test")
    monkeypatch.setattr(cli.Settings, "from_env", classmethod(lambda cls: settings))
    monkeypatch.setattr(cli, "create_postgres_engine", lambda _: object())
    monkeypatch.setattr(cli, "PostgresAuthRepository", lambda _: repository)
    monkeypatch.setenv("BOOTSTRAP_ADMIN_USERNAME", "initial-admin")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_DISPLAY_NAME", "首任管理员（脱敏测试）")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", TEST_PASSWORD)

    assert cli.bootstrap_admin() == 0
    first_output = capsys.readouterr()
    assert TEST_PASSWORD not in first_output.out
    assert TEST_PASSWORD not in first_output.err
    assert '"status": "created"' in first_output.out

    assert cli.bootstrap_admin() == 3
    second_output = capsys.readouterr()
    assert TEST_PASSWORD not in second_output.out
    assert TEST_PASSWORD not in second_output.err
    assert "admin_already_exists" in second_output.err
    events = repository.list_security_events()
    assert [event["outcome"] for event in events if event["event_type"] == "auth.bootstrap_admin"] == ["success", "rejected"]


def test_controlled_demo_password_reset_revokes_sessions_and_never_prints_password(monkeypatch, capsys):
    repository = InMemoryAuthRepository()
    accounts = [
        repository.add_user("d1-steven-demo", TEST_PASSWORD, {"operator"}),
        repository.add_user("d1-approver-demo", TEST_PASSWORD, {"approver"}),
        repository.add_user("d1-admin-demo", TEST_PASSWORD, {"admin"}),
    ]
    for account in accounts:
        repository.create_session(account.id, f"token-{account.id}", 30, 8)
    reset_password = "demo-reset-password"
    settings = Settings(
        app_env="development",
        auth_mode="session",
        demo_seed_enabled=False,
        database_url="postgresql+psycopg://demo@127.0.0.1/puiying_steven_demo",
        file_storage_root="./data/development",
        allowed_origins=("https://localhost:15443",),
    )
    monkeypatch.setattr(cli.Settings, "from_env", classmethod(lambda cls: settings))
    monkeypatch.setattr(cli, "create_postgres_engine", lambda _: object())
    monkeypatch.setattr(cli, "PostgresAuthRepository", lambda _: repository)
    monkeypatch.setenv("DEMO_PASSWORD_RESET_CONFIRM", "RESET_LOCAL_DEMO_ONLY")
    monkeypatch.setenv(
        "DEMO_PASSWORD_RESET_USERNAMES",
        "d1-steven-demo,d1-approver-demo,d1-admin-demo",
    )
    monkeypatch.setenv("DEMO_PASSWORD_RESET_PASSWORD", reset_password)

    assert cli.reset_demo_passwords() == 0
    output = capsys.readouterr()
    assert reset_password not in output.out
    assert reset_password not in output.err
    assert '"status": "reset"' in output.out
    assert all(
        repository.authenticate(account.username, reset_password, 5, 15).outcome == "success"
        for account in accounts
    )
    assert all(session["revoked_at"] is not None for session in repository.list_sessions())
    reset_events = [
        event for event in repository.list_security_events()
        if event["event_type"] == "auth.demo_password_reset"
    ]
    assert len(reset_events) == 3


def test_demo_account_sync_keeps_exactly_two_named_single_role_accounts_and_revokes_sessions():
    repository = InMemoryAuthRepository()
    legacy_operator = repository.add_user("steven", TEST_PASSWORD, {"operator"}, display_name="旧操作员")
    extra_user = repository.add_user("temporary-demo-user", TEST_PASSWORD, {"operator"}, display_name="临时用户")
    repository.create_session(legacy_operator.id, "legacy-session-token", 30, 8)
    repository.create_session(extra_user.id, "temporary-session-token", 30, 8)
    synchronized_password = "synchronized-test-password"

    result = repository.sync_demo_accounts(synchronized_password)

    assert result["previous_user_count"] == 2
    assert result["current_user_count"] == 2
    assert result["sessions_revoked"] == 2
    assert repository.list_sessions() == []
    accounts = {
        account["username"]: account
        for account in repository.list_users()
    }
    assert set(accounts) == {"Steven", "approve"}
    assert accounts["Steven"]["display_name"] == "Steven"
    assert accounts["Steven"]["roles"] == ["operator"]
    assert accounts["approve"]["display_name"] == "审批人"
    assert accounts["approve"]["roles"] == ["approver"]
    assert all(
        repository.authenticate(username, synchronized_password, 5, 15).outcome == "success"
        for username in accounts
    )


def test_demo_account_sync_cli_rejects_wrong_boundary_and_never_prints_password(monkeypatch, capsys):
    password = "synchronized-test-password"
    settings = Settings(
        app_env="test",
        auth_mode="session",
        demo_seed_enabled=False,
        database_url="postgresql+psycopg://puiying_steven_demo_app@127.0.0.1/puiying_steven_demo",
        file_storage_root="./data/test",
    )
    monkeypatch.setattr(cli.Settings, "from_env", classmethod(lambda cls: settings))
    monkeypatch.setenv("DEMO_ACCOUNT_SYNC_CONFIRM", "SYNC_LOCAL_REDACTED_DEMO_ONLY")
    monkeypatch.setenv("DEMO_ACCOUNT_SYNC_PASSWORD", password)

    assert cli.sync_demo_accounts() == 2
    output = capsys.readouterr()
    assert password not in output.out
    assert password not in output.err
    assert "demo_account_sync_environment_invalid" in output.err


def test_demo_account_sync_cli_succeeds_without_secret_output(monkeypatch, capsys):
    repository = InMemoryAuthRepository()
    password = "synchronized-test-password"
    settings = Settings(
        app_env="development",
        auth_mode="session",
        demo_seed_enabled=False,
        database_url="postgresql+psycopg://puiying_steven_demo_app@127.0.0.1/puiying_steven_demo",
        file_storage_root="./data/development",
        allowed_origins=("https://localhost:15443",),
    )
    monkeypatch.setattr(cli.Settings, "from_env", classmethod(lambda cls: settings))
    monkeypatch.setattr(cli, "create_postgres_engine", lambda _: object())
    monkeypatch.setattr(cli, "PostgresAuthRepository", lambda _: repository)
    monkeypatch.setenv("DEMO_ACCOUNT_SYNC_CONFIRM", "SYNC_LOCAL_REDACTED_DEMO_ONLY")
    monkeypatch.setenv("DEMO_ACCOUNT_SYNC_PASSWORD", password)

    assert cli.sync_demo_accounts() == 0
    output = capsys.readouterr()
    assert password not in output.out
    assert password not in output.err
    assert '"status": "synchronized"' in output.out
    assert '"current_user_count": 2' in output.out
