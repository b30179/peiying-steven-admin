from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.modules.accounts.repository import InMemoryAuthRepository


def mock_client(identity: str = "steven") -> TestClient:
    settings = Settings(app_env="test", auth_mode="mock", demo_seed_enabled=True, mock_identity=identity)
    return TestClient(create_app(settings, InMemoryAuthRepository()))


def test_health_uses_standard_envelope() -> None:
    response = mock_client().get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["status"] == "ok"
    assert payload["data"]["auth_mode"] == "mock"
    assert payload["pagination"] is None
    assert payload["request_id"]


def test_steven_dashboard_uses_mock_repository_and_envelope() -> None:
    response = mock_client("steven").get("/api/v1/steven/dashboard")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["data"]["metrics"]) == 4
    assert len(payload["data"]["priority_todos"]) == 5
    assert payload["data"]["ai_enabled"] is False


def test_approver_can_read_dashboard_but_cannot_create_quote() -> None:
    client = mock_client("approver")
    assert client.get("/api/v1/steven/dashboard").status_code == 200
    response = client.post("/api/v1/steven/quotes", json={"subject": "禁止修改", "currency": "HKD"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_regular_steven_cannot_read_audit_events() -> None:
    response = mock_client("steven").get("/api/v1/audit/events")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_admin_can_read_dashboard_audit_event() -> None:
    mock_client("steven").get("/api/v1/steven/dashboard")
    response = mock_client("admin").get("/api/v1/audit/events")
    assert response.status_code == 200
    events = response.json()["data"]
    assert any(event["action"] == "dashboard.view" and event["actor"] == "mock-steven" for event in events)

def test_request_id_accepts_only_bounded_safe_characters() -> None:
    accepted = "A" + "b" * 127
    accepted_response = mock_client().get("/health", headers={"X-Request-Id": accepted})
    assert accepted_response.json()["request_id"] == accepted

    for rejected in ("A" * 129, "contains space", "bad/value", "bad@value"):
        response = mock_client().get("/health", headers={"X-Request-Id": rejected})
        request_id = response.json()["request_id"]
        assert request_id != rejected
        assert len(request_id) <= 128

