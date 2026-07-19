from __future__ import annotations

import hashlib

import pytest
from pydantic import ValidationError

from app.core.api_response import ApiError
from app.modules.document_intelligence.adapters import (
    DeepSeekStructuringAdapter,
    MockTenderProofreadingAdapter,
    load_deepseek_api_key,
)
from app.modules.document_intelligence.schemas import (
    AiStructuringRequest,
    EvidenceLocation,
    TenderProofreadingCandidate,
)
from app.modules.platform import user_features as user_features_module
from app.modules.platform.user_features import UserFeaturesService
from app.modules.steven.tender_proofreading_service import TenderProofreadingService, apply_proofreading_replacement


def proofreading_request(body: str = "脫敏 Demo service 草稿") -> AiStructuringRequest:
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return AiStructuringRequest(
        document_type="tender_document",
        purpose="tender_proofreading",
        schema_name="steven.s1.tender_proofreading",
        schema_version="1.0",
        request_id="request-proofreading-test",
        sanitized_text=f"DOCUMENT_SHA256:{digest}\nDOCUMENT_CONTENT:\n{body}",
        evidence=[EvidenceLocation(field_path="rendered_body", page=1, original_text=body, bbox=[0, 0, 1, 1], confidence=1)],
    )


def test_proofreading_replacement_applies_only_unique_current_text():
    body = "截止日期：2026-07-20\n预算范围：HKD 1000.00 - 3000.00"
    updated = apply_proofreading_replacement(body, "2026-07-20", "2026年07月20日")
    assert updated == "截止日期：2026年07月20日\n预算范围：HKD 1000.00 - 3000.00"


def test_proofreading_replacement_rejects_missing_or_ambiguous_text():
    with pytest.raises(ApiError) as missing:
        apply_proofreading_replacement("当前草稿", "过期原文", "建议")
    assert missing.value.code == "proofreading_original_not_found"

    with pytest.raises(ApiError) as ambiguous:
        apply_proofreading_replacement("重复片段；重复片段", "重复片段", "建议")
    assert ambiguous.value.code == "proofreading_original_ambiguous"


def test_proofreading_replacement_allows_explicit_no_op_acceptance():
    body = "脱敏设施保养服务"
    assert apply_proofreading_replacement(body, body, body) == body



def test_mock_proofreading_returns_strict_needs_review_payload_shape():
    result = MockTenderProofreadingAdapter().structure(proofreading_request())
    candidate = TenderProofreadingCandidate.model_validate(result.candidate)
    assert result.source == "mock"
    assert candidate.summary == {"error": 0, "warning": 1, "info": 0, "total": 1}
    assert candidate.issues[0].severity == "warning"


def test_proofreading_schema_forbids_extra_fields_and_invalid_summary():
    digest = "a" * 64
    with pytest.raises(ValidationError):
        TenderProofreadingCandidate.model_validate({
            "document_sha256": digest,
            "issues": [],
            "summary": {"error": 0, "warning": 0, "info": 0, "total": 0},
            "approval": "approved",
        })
    with pytest.raises(ValidationError):
        TenderProofreadingCandidate.model_validate({
            "document_sha256": digest,
            "issues": [],
            "summary": {"error": 1, "warning": 0, "info": 0, "total": 1},
        })


def test_deepseek_secret_loader_reads_only_named_section(monkeypatch, tmp_path):
    secret_file = tmp_path / "keys.md"
    secret_file.write_text("## Other\nKey: ignored\n\n## DeepSeek\nKey: sk-mock-redacted-testing\n", encoding="utf-8")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY_FILE", str(secret_file))
    assert load_deepseek_api_key() == "sk-mock-redacted-testing"


def test_deepseek_adapter_validates_json_and_never_accepts_forbidden_fields():
    request = proofreading_request()
    digest = request.sanitized_text.split("DOCUMENT_SHA256:", 1)[1].splitlines()[0]
    captured = {}

    def transport(payload):
        captured["url"] = payload["url"]
        captured["authorization_present"] = payload["headers"].get("Authorization", "").startswith("Bearer ")
        return {"choices": [{"message": {"content": (
            '{"document_sha256":"' + digest + '","issues":[],"summary":{"error":0,"warning":0,"info":0,"total":0}}'
        )}}]}

    adapter = DeepSeekStructuringAdapter(
        "https://api.deepseek.com/v1",
        "deepseek-chat",
        10,
        transport,
        api_key="sk-mock-redacted-testing",
    )
    result = adapter.structure(request)
    assert captured == {"url": "https://api.deepseek.com/v1/chat/completions", "authorization_present": True}
    assert result.source == "live"
    assert result.candidate["issues"] == []


class _Mappings:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _Result:
    def __init__(self, row):
        self._row = row

    def mappings(self):
        return _Mappings(self._row)


class _Connection:
    def __init__(self, row):
        self._row = row

    def execute(self, *_args, **_kwargs):
        return _Result(self._row)


class _Begin:
    def __init__(self, row):
        self._connection = _Connection(row)

    def __enter__(self):
        return self._connection

    def __exit__(self, *_args):
        return False


class _Engine:
    def __init__(self, row):
        self._row = row

    def begin(self):
        return _Begin(self._row)


def test_live_proofreading_rejects_non_demo_document_before_provider_call():
    service = TenderProofreadingService(
        _Engine({"id": "tender-1", "rendered_body": "非 Demo 正文", "is_demo": False}),
        MockTenderProofreadingAdapter(),
        enabled=True,
        provider="deepseek",
        model="deepseek-chat",
    )
    with pytest.raises(ApiError) as captured:
        service.start("tender-1", "user-1", "request-1")
    assert captured.value.code == "ai_requires_redacted_demo"


def test_disabled_proofreading_returns_explicit_manual_fallback():
    service = TenderProofreadingService(None, None, enabled=False, provider="mock", model="fixture-v1")
    with pytest.raises(ApiError) as captured:
        service.start("tender-1", "user-1", "request-1")
    assert captured.value.code == "ai_structuring_disabled"


class _PasswordResult:
    def __init__(self, row=None):
        self._row = row

    def mappings(self):
        return _Mappings(self._row)


class _PasswordConnection:
    def __init__(self):
        self.calls = []

    def execute(self, statement, parameters=None):
        sql = str(statement)
        self.calls.append((sql, parameters or {}))
        if "SELECT password_hash" in sql:
            return _PasswordResult({"password_hash": "old-hash"})
        return _PasswordResult()


class _PasswordBegin:
    def __init__(self, connection):
        self._connection = connection

    def __enter__(self):
        return self._connection

    def __exit__(self, *_args):
        return False


class _PasswordEngine:
    def __init__(self):
        self.connection = _PasswordConnection()

    def begin(self):
        return _PasswordBegin(self.connection)


class _AuditStub:
    def append(self, **_kwargs):
        return None


@pytest.mark.parametrize(
    ("session_id", "expected_session_parameter"),
    [(None, False), ("session-current", True)],
)
def test_change_password_uses_unambiguous_session_revocation_sql(monkeypatch, session_id, expected_session_parameter):
    engine = _PasswordEngine()
    monkeypatch.setattr(user_features_module, "verify_password", lambda password, _password_hash: password == "old-password")
    monkeypatch.setattr(user_features_module, "hash_password", lambda _password: "new-hash")
    monkeypatch.setattr(user_features_module, "PostgresAuditRepository", lambda _connection: _AuditStub())

    UserFeaturesService(engine).change_password(
        user_id="user-1",
        session_id=session_id,
        old_password="old-password",
        new_password="new-password",
        request_id="request-1",
    )

    revoke_calls = [call for call in engine.connection.calls if "UPDATE auth_sessions" in call[0]]
    assert len(revoke_calls) == 1
    revoke_sql, revoke_parameters = revoke_calls[0]
    assert ("id<>:session_id" in revoke_sql) is expected_session_parameter
    assert ("session_id" in revoke_parameters) is expected_session_parameter
