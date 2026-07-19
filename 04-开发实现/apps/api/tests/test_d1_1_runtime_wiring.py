from fastapi.testclient import TestClient

import app.main as main_module
from app.core.audit import PostgresAuditRepository
from app.core.config import Settings
from app.modules.accounts.repository import PostgresAuthRepository


def test_development_session_runtime_uses_postgres_without_exposing_connection_string(monkeypatch, tmp_path):
    fake_engine = object()
    monkeypatch.setattr(main_module, "create_postgres_engine", lambda _: fake_engine)
    settings = Settings(
        app_env="development",
        auth_mode="session",
        demo_seed_enabled=False,
        database_url="postgresql+psycopg://demo-user:do-not-expose@127.0.0.1:5432/puiying_steven_demo",
        file_storage_root=str(tmp_path),
        allowed_origins=("http://127.0.0.1:3000",),
    )

    application = main_module.create_app(settings)

    assert isinstance(application.state.auth_repository, PostgresAuthRepository)
    assert isinstance(application.state.audit_repository, PostgresAuditRepository)
    assert isinstance(application.state.quote_application, main_module.LazyPostgresQuoteApplication)
    assert application.state.postgres_engine is fake_engine

    response = TestClient(application).get("/health")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["auth_mode"] == "session"
    assert payload["persistence"] == {
        "mode": "postgresql",
        "database": "puiying_steven_demo",
        "session_store": "postgresql",
            "audit_store": "postgresql",
            "quote_store": "postgresql",
            "tender_store": "postgresql",
            "inventory_store": "postgresql",
        }
    assert "do-not-expose" not in response.text
    assert "postgresql+psycopg" not in response.text
