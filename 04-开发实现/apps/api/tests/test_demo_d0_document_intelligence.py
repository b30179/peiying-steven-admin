from __future__ import annotations

from datetime import date
from decimal import Decimal
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.api_response import ApiError
from app.core.audit import AuditRepository
from app.core.config import Settings
from app.main import create_app
from app.modules.accounts.repository import InMemoryAuthRepository
from app.modules.document_intelligence.adapters import (
    AzureDocumentIntelligenceAdapter,
    DeepSeekStructuringAdapter,
    MockAiStructuringAdapter,
    MockOcrAdapter,
    build_sanitized_ai_input,
    build_system_prompt,
    map_azure_invoice_response,
    validate_structured_candidate,
)
from app.modules.document_intelligence.repository import InMemoryDocumentIntelligenceRepository
from app.modules.document_intelligence.schemas import (
    AiStructuringRequest,
    CandidateRevisionRequest,
    EvidenceLocation,
    OcrRequest,
    OcrResult,
    ReviewCandidate,
    ScanImportCreateRequest,
)
from app.modules.document_intelligence.service import DocumentIntelligenceService
from app.modules.document_intelligence.storage import InMemoryDocumentFileStorage, LocalAppendOnlyDocumentFileStorage
from app.modules.steven.quote_excel import LocalAppendOnlyQuoteStorage, QuoteExcelExporter, QuoteImportParser
from app.modules.steven.quote_repository import StevenQuoteRepository
from app.modules.steven.quote_schemas import QuoteCreateRequest
from app.modules.steven.quote_service import StevenQuoteService
from app.modules.steven.scan_import_application import InMemoryScanImportUnitOfWork, StevenScanImportApplicationService


ITEMS = [
    ("ITEM-001", "A4 影印纸", "80gsm，500 张/包", "20", "包"),
    ("ITEM-002", "蓝色原子笔", "0.7mm", "100", "支"),
    ("ITEM-003", "订书钉", "24/6，1000 枚/盒", "50", "盒"),
    ("ITEM-004", "A4 文件夹", "透明，40 页", "60", "个"),
    ("ITEM-005", "白板笔", "黑色，可擦", "30", "支"),
]
SUPPLIERS = [
    ("SUP-A", "文具供应商甲（脱敏）", "2026-08-15", "120", "80", ["42", "4.2", "8.5", "6", "12"]),
    ("SUP-B", "文具供应商乙（脱敏）", "2026-08-20", "180", "75", ["40", "4.5", "8", "6.2", "11.5"]),
    ("SUP-C", "文具供应商丙（脱敏）", "2026-08-10", "90", "100", ["43", "4", "8.2", "5.8", "12.5"]),
]


def quotation_candidate(index: int = 0, *, currency: str = "HKD", valid_until: str | None = None, item_count: int = 5) -> dict:
    code, name, default_valid_until, freight, tax, prices = SUPPLIERS[index]
    return {
        "supplier_code": code,
        "supplier_name": name,
        "currency": currency,
        "valid_until": valid_until or default_valid_until,
        "freight": freight,
        "tax": tax,
        "items": [
            {
                "item_code": item_code,
                "item": item,
                "specification": specification,
                "qty": qty,
                "unit": unit,
                "unit_price": prices[item_index],
            }
            for item_index, (item_code, item, specification, qty, unit) in enumerate(ITEMS[:item_count])
        ],
    }


def quotation_batch_candidate(indices: tuple[int, ...] = (0, 1, 2)) -> dict:
    return {"quotes": [quotation_candidate(index) for index in indices]}


def make_document_service(candidate: dict | None = None, ocr=None, ai=None):
    repository = InMemoryDocumentIntelligenceRepository()
    storage = InMemoryDocumentFileStorage()
    ocr_result = OcrResult(
        provider="mock",
        model="fixture-v1",
        text="脱敏供应商报价",
        evidence=[EvidenceLocation(field_path="supplier_name", page=1, original_text="脱敏供应商", bbox=[10, 10, 100, 25], confidence=0.98)],
        source="mock",
    )
    return DocumentIntelligenceService(
        repository,
        storage,
        ocr or MockOcrAdapter(ocr_result),
        ai or MockAiStructuringAdapter(candidate or quotation_candidate()),
    )


def add_review_candidate(repository, quote_id: str, payload: dict) -> ReviewCandidate:
    candidate = ReviewCandidate(
        source_file_id="sanitized-file",
        document_type="supplier_quotation",
        purpose="quotation_extraction",
        schema_name="steven.s2.quotation",
        schema_version="1.0",
        provider="mock+mock",
        model="fixture-v1+fixture-v1",
        status="needs_review",
        candidate_json=validate_structured_candidate("steven.s2.quotation", payload),
        target_object_type="steven_quote_job",
        target_object_id=quote_id,
        request_id="d0-test-request",
    )
    return repository.add_candidate(candidate)


def make_scan_application(tmp_path):
    documents = InMemoryDocumentIntelligenceRepository()
    quote_repository = StevenQuoteRepository(seed_demo=False)
    quote_audit = AuditRepository()
    exporter = QuoteExcelExporter(tmp_path)
    quote_storage = LocalAppendOnlyQuoteStorage(exporter.data_root)
    quote_service = StevenQuoteService(quote_repository, quote_audit, QuoteImportParser(), exporter, quote_storage)
    quote = quote_service.create_quote(QuoteCreateRequest(subject="D0 脱敏扫描导入", currency="HKD", is_demo=True), "steven.test")
    application = StevenScanImportApplicationService(
        InMemoryScanImportUnitOfWork(documents, quote_repository, quote_audit),
        QuoteImportParser(),
        exporter,
        quote_storage,
    )
    return application, documents, quote_repository, quote_audit, quote.id


def test_azure_adapter_validates_configuration_and_maps_mock_transport():
    with pytest.raises(ValueError, match="invalid_azure_endpoint"):
        AzureDocumentIntelligenceAdapter("http://unsafe.invalid", "prebuilt-invoice", 30, lambda _: {})
    with pytest.raises(ValueError, match="unsupported_azure_model"):
        AzureDocumentIntelligenceAdapter("https://azure.invalid", "other", 30, lambda _: {})
    with pytest.raises(ValueError, match="invalid_timeout"):
        AzureDocumentIntelligenceAdapter("https://azure.invalid", "prebuilt-invoice", 0, lambda _: {})

    captured: dict = {}

    def transport(request: dict) -> dict:
        captured.update(request)
        return {"analyzeResult": {"pages": [{"pageNumber": 2, "lines": [{"content": "SUP-A HKD", "polygon": [1, 2, 3, 4], "confidence": 0.91}]}]}}

    adapter = AzureDocumentIntelligenceAdapter("https://azure.invalid/", "prebuilt-invoice", 12, transport, api_key="test-only-secret")
    result = adapter.extract(OcrRequest(
        file_id="file-1", document_type="supplier_quotation", purpose="quotation_extraction",
        request_id="request-1", content=b"sanitized-pdf", mime_type="application/pdf",
    ))
    assert captured["url"].endswith("prebuilt-invoice:analyze?api-version=2024-11-30")
    assert captured["timeout_seconds"] == 12
    assert result.provider == "azure_document_intelligence" and result.source == "live"
    assert result.evidence[0].page == 2 and result.evidence[0].bbox == [1.0, 2.0, 3.0, 4.0]


def test_azure_mapper_accepts_point_polygon_objects():
    result = map_azure_invoice_response({"pages": [{"lines": [{
        "content": "HKD 2,605.00",
        "polygon": [{"x": 1, "y": 2}, {"x": 3, "y": 4}],
        "confidence": 0.8,
    }]}]})
    assert result.text == "HKD 2,605.00"
    assert result.evidence[0].bbox == [1.0, 2.0, 3.0, 4.0]


def test_deepseek_adapter_uses_strict_json_and_sanitized_input():
    captured: dict = {}

    def transport(request: dict) -> dict:
        captured.update(request)
        return {"choices": [{"message": {"content": json.dumps(quotation_candidate(), ensure_ascii=False)}}]}

    adapter = DeepSeekStructuringAdapter("https://deepseek.invalid/v1", "deepseek-chat", 20, transport, api_key="test-only-secret")
    request = AiStructuringRequest(
        document_type="supplier_quotation", purpose="quotation_extraction", schema_name="steven.s2.quotation",
        schema_version="1.0", request_id="request-2",
        sanitized_text="contact@example.test +852 9123 4567 脱敏报价",
        evidence=[],
    )
    result = adapter.structure(request)
    user_content = captured["json"]["messages"][1]["content"]
    assert "contact@example.test" not in user_content and "9123 4567" not in user_content
    assert "[REDACTED_EMAIL]" in user_content and "[REDACTED_PHONE]" in user_content
    assert result.candidate["quotes"][0]["supplier_code"] == "SUP-A" and result.source == "live"
    prompt = captured["json"]["messages"][0]["content"]
    assert "one quotes[] entry per supplier column" in prompt
    assert "never use REVIEW-PLACEHOLDER" in prompt


def test_document_intelligence_request_size_limits():
    common = {
        "document_type": "supplier_quotation",
        "purpose": "quotation_extraction",
        "schema_name": "steven.s2.quotation",
        "schema_version": "1.0",
        "request_id": "request-size-limits",
    }
    evidence = EvidenceLocation(
        field_path="supplier_name",
        page=1,
        original_text="脱敏供应商",
        bbox=[10, 10, 100, 25],
        confidence=0.98,
    )

    AiStructuringRequest(**common, sanitized_text="x" * 50_000, evidence=[evidence] * 100)
    CandidateRevisionRequest(revision={"supplier_name": "脱敏供应商"})

    with pytest.raises(ValidationError):
        AiStructuringRequest(**common, sanitized_text="x" * 50_001, evidence=[])
    with pytest.raises(ValidationError):
        AiStructuringRequest(**common, sanitized_text="ok", evidence=[evidence] * 101)
    with pytest.raises(ValidationError):
        CandidateRevisionRequest(revision={})
    with pytest.raises(ValidationError):
        CandidateRevisionRequest(revision={str(index): index for index in range(201)})


def test_candidate_schema_rejects_unknown_and_ai_decision_fields():
    unknown = {**quotation_candidate(), "unexpected": "blocked"}
    with pytest.raises(ValidationError):
        validate_structured_candidate("steven.s2.quotation", unknown)
    forbidden = {**quotation_candidate(), "recommended_supplier_id": "SUP-A"}
    with pytest.raises(ValueError, match="forbidden_ai_decision_field"):
        validate_structured_candidate("steven.s2.quotation", forbidden)
    with pytest.raises(ValueError, match="schema_not_enabled"):
        validate_structured_candidate("steven.s1.future", quotation_candidate())


def test_document_flow_stops_at_needs_review_and_preserves_evidence():
    service = make_document_service()
    stored = service.store_file(
        filename="sanitized.pdf", content=b"sanitized demo only", mime_type="application/pdf",
        document_type="supplier_quotation", purpose="quotation_extraction", actor="steven.test", request_id="request-3",
    )
    candidate = service.create_scan_candidate_for_file(ScanImportCreateRequest(quote_id="quote-1", source_file_id=stored.id), "request-3")
    assert candidate.status == "needs_review"
    assert candidate.reviewer_id is None and candidate.human_revision_json is None
    assert candidate.provider == "mock+mock" and candidate.evidence[0].page == 1
    assert service.get_job(candidate.ocr_job_id).status == "needs_review"
    assert service.get_job(candidate.ai_job_id).status == "needs_review"
    assert service.read_file(stored.id)[1] == b"sanitized demo only"


def test_provider_failure_marks_candidate_failed_without_live_fallback():
    class FailingAi:
        def structure(self, request):
            del request
            raise RuntimeError("provider_unavailable")

    service = make_document_service(ai=FailingAi())
    stored = service.store_file(
        filename="sanitized.pdf", content=b"fixture", mime_type="application/pdf",
        document_type="supplier_quotation", purpose="quotation_extraction", actor="steven.test", request_id="request-4",
    )
    with pytest.raises(RuntimeError, match="provider_unavailable"):
        service.create_scan_candidate_for_file(ScanImportCreateRequest(quote_id="quote-1", source_file_id=stored.id), "request-4")
    candidate = service.list_candidates("quote-1")[0]
    assert candidate.status == "failed" and candidate.warnings == ["provider_processing_failed"]
    assert service.get_job(candidate.ai_job_id).status == "failed"


def test_candidate_revision_rejection_and_state_machine():
    service = make_document_service()
    stored = service.store_file(
        filename="sanitized.pdf", content=b"fixture", mime_type="application/pdf",
        document_type="supplier_quotation", purpose="quotation_extraction", actor="steven.test", request_id="request-5",
    )
    candidate = service.create_scan_candidate_for_file(ScanImportCreateRequest(quote_id="quote-1", source_file_id=stored.id), "request-5")
    from app.modules.document_intelligence.schemas import CandidateRevisionRequest
    revised_payload = quotation_candidate()
    revised_payload["freight"] = "125"
    revised = service.revise_candidate(candidate.id, CandidateRevisionRequest(revision=revised_payload), "steven.reviewer")
    assert revised.status == "needs_review" and revised.human_revision_json["quotes"][0]["freight"] == "125"
    rejected = service.reject_candidate(candidate.id, "steven.reviewer")
    assert rejected.status == "rejected" and rejected.reviewer_id == "steven.reviewer"
    with pytest.raises(ApiError, match="候选当前不可修改"):
        service.revise_candidate(candidate.id, CandidateRevisionRequest(revision=revised_payload), "steven.reviewer")


def test_three_confirmed_candidates_create_exact_3x5_and_expected_totals(tmp_path):
    application, documents, quote_repository, audit, quote_id = make_scan_application(tmp_path)
    candidates = [add_review_candidate(documents, quote_id, quotation_candidate(index)) for index in range(3)]
    result = None
    for candidate in candidates:
        result = application.confirm_scan_candidate(candidate.id, quote_id, "steven.reviewer")
    assert result is not None
    assert len(result.items) == 5 and len(result.suppliers) == 3 and len(result.offer_lines) == 15
    assert result.comparison.comparison_allowed is True
    assert [(entry.supplier_name, entry.subtotal, entry.freight, entry.tax, entry.total) for entry in result.comparison.ranking] == [
        ("文具供应商丙（脱敏）", 2393, 90, 100, 2583),
        ("文具供应商甲（脱敏）", 2405, 120, 80, 2605),
        ("文具供应商乙（脱敏）", 2367, 180, 75, 2622),
    ]
    assert all(documents.get_candidate(candidate.id).status == "confirmed" for candidate in candidates)
    assert any(event["action"] == "quote.scan_candidate_confirm" for event in audit.list_for_object(quote_id))
    assert len(quote_repository.offers_for(quote_id)) == 15


def test_one_multi_supplier_candidate_creates_exact_3x5_without_column_mix(tmp_path):
    application, documents, quote_repository, audit, quote_id = make_scan_application(tmp_path)
    candidate = add_review_candidate(documents, quote_id, quotation_batch_candidate())

    result = application.confirm_scan_candidate(candidate.id, quote_id, "steven.reviewer")

    assert len(result.items) == 5 and len(result.suppliers) == 3 and len(result.offer_lines) == 15
    supplier_ids = {supplier.supplier_code: supplier.id for supplier in result.suppliers}
    item_ids = {item.item_code: item.id for item in result.items}
    prices = {(line.quote_supplier_id, line.quote_item_id): line.unit_price for line in result.offer_lines}
    for supplier_code, _, _, _, _, expected_prices in SUPPLIERS:
        for item_index, (item_code, *_rest) in enumerate(ITEMS):
            assert prices[(supplier_ids[supplier_code], item_ids[item_code])] == Decimal(expected_prices[item_index])
    event = next(event for event in audit.list_for_object(quote_id) if event["action"] == "quote.scan_candidate_confirm")
    assert event["before_after"]["after"]["supplier_count"] == 3
    assert event["before_after"]["after"]["supplier_codes"] == ["SUP-A", "SUP-B", "SUP-C"]
    assert documents.get_candidate(candidate.id).status == "confirmed"
    assert len(quote_repository.offers_for(quote_id)) == 15


def test_multi_supplier_candidate_requires_dates_and_rolls_back_all_writes(tmp_path):
    application, documents, quote_repository, audit, quote_id = make_scan_application(tmp_path)
    payload = quotation_batch_candidate()
    payload["quotes"][1]["valid_until"] = "REVIEW-PLACEHOLDER"
    candidate = add_review_candidate(documents, quote_id, payload)

    with pytest.raises(ApiError) as captured:
        application.confirm_scan_candidate(candidate.id, quote_id, "steven.reviewer")

    assert captured.value.code == "candidate_valid_until_required"
    assert documents.get_candidate(candidate.id).status == "needs_review"
    assert quote_repository.items_for(quote_id) == []
    assert quote_repository.suppliers_for(quote_id) == []
    assert quote_repository.offers_for(quote_id) == []
    assert [event["action"] for event in audit.list_for_object(quote_id)] == ["quote.create"]


def test_multi_supplier_candidate_rejects_duplicate_supplier_and_mismatched_items(tmp_path):
    for mutate, expected_code in [
        (lambda payload: payload["quotes"][1].update(supplier_code="SUP-A"), "duplicate_supplier_code"),
        (lambda payload: payload["quotes"][1]["items"].pop(), "candidate_item_set_mismatch"),
    ]:
        application, documents, quote_repository, audit, quote_id = make_scan_application(tmp_path)
        payload = quotation_batch_candidate()
        mutate(payload)
        candidate = add_review_candidate(documents, quote_id, payload)

        with pytest.raises(ApiError) as captured:
            application.confirm_scan_candidate(candidate.id, quote_id, "steven.reviewer")

        assert captured.value.code == expected_code
        assert documents.get_candidate(candidate.id).status == "needs_review"
        assert quote_repository.items_for(quote_id) == []
        assert quote_repository.suppliers_for(quote_id) == []
        assert quote_repository.offers_for(quote_id) == []
        assert [event["action"] for event in audit.list_for_object(quote_id)] == ["quote.create"]


def test_missing_item_currency_mismatch_and_duplicate_supplier_roll_back(tmp_path):
    application, documents, quote_repository, audit, quote_id = make_scan_application(tmp_path)
    first = add_review_candidate(documents, quote_id, quotation_candidate(0))
    application.confirm_scan_candidate(first.id, quote_id, "steven.reviewer")
    baseline = (len(quote_repository.items_for(quote_id)), len(quote_repository.suppliers_for(quote_id)), len(quote_repository.offers_for(quote_id)), len(audit.list()))

    cases = [
        (quotation_candidate(1, item_count=4), "candidate_item_set_mismatch"),
        (quotation_candidate(1, currency="USD"), "candidate_currency_mismatch"),
        (quotation_candidate(0), "duplicate_supplier_code"),
    ]
    for payload, expected_code in cases:
        candidate = add_review_candidate(documents, quote_id, payload)
        with pytest.raises(ApiError) as captured:
            application.confirm_scan_candidate(candidate.id, quote_id, "steven.reviewer")
        assert captured.value.code == expected_code
        assert documents.get_candidate(candidate.id).status == "needs_review"
        assert (len(quote_repository.items_for(quote_id)), len(quote_repository.suppliers_for(quote_id)), len(quote_repository.offers_for(quote_id)), len(audit.list())) == baseline


def test_expired_candidate_is_confirmed_only_with_visible_warning(tmp_path):
    application, documents, _, _, quote_id = make_scan_application(tmp_path)
    candidate = add_review_candidate(documents, quote_id, quotation_candidate(0, valid_until="2020-01-01"))
    quote = application.confirm_scan_candidate(candidate.id, quote_id, "steven.reviewer")
    assert quote.comparison.comparison_allowed is True
    assert quote.comparison.warnings == ["文具供应商甲（脱敏） 的报价已过期。"]
    assert quote.recommended_supplier_id is None


def test_append_only_document_storage_checks_hash_and_path(tmp_path):
    storage = LocalAppendOnlyDocumentFileStorage(tmp_path)
    content = b"sanitized document"
    import hashlib
    digest = hashlib.sha256(content).hexdigest()
    storage.put("demo-documents/aa/file.bin", content, digest)
    storage.put("demo-documents/aa/file.bin", content, digest)
    assert storage.read("demo-documents/aa/file.bin") == content
    with pytest.raises(ValueError, match="hash_mismatch"):
        storage.put("demo-documents/aa/bad.bin", content, "0" * 64)
    with pytest.raises(ValueError, match="outside_root"):
        storage.read("../outside.bin")


def test_api_can_be_explicitly_disabled_and_cross_role_is_denied():
    disabled_settings = Settings(
        app_env="test", auth_mode="mock", demo_seed_enabled=True, mock_identity="steven",
        ocr_enabled=False, ai_structuring_enabled=False,
    )
    disabled = TestClient(create_app(disabled_settings, InMemoryAuthRepository()))
    response = disabled.post("/api/v1/steven/files", files={"file": ("sanitized.pdf", b"fixture", "application/pdf")})
    assert response.status_code == 409 and response.json()["error"]["code"] == "document_intelligence_disabled"

    enabled_settings = Settings(
        app_env="test", auth_mode="mock", demo_seed_enabled=True, mock_identity="approver",
        demo_profile_enabled=True, ocr_enabled=True, ai_structuring_enabled=True,
    )
    denied = TestClient(create_app(enabled_settings, InMemoryAuthRepository()))
    response = denied.post("/api/v1/steven/files", files={"file": ("sanitized.pdf", b"fixture", "application/pdf")})
    assert response.status_code == 403 and response.json()["error"]["code"] == "forbidden"


def test_d2_document_intelligence_defaults_use_local_paddle_and_enabled_structuring():
    settings = Settings(app_env="test", auth_mode="mock", demo_seed_enabled=True, mock_identity="steven")
    assert settings.demo_profile_enabled is True
    assert settings.ocr_enabled is True and settings.ocr_provider == "paddle"
    assert settings.ai_structuring_enabled is True


def test_mock_and_cached_sources_are_explicit_and_migration_is_0007():
    assert MockOcrAdapter().extract(OcrRequest(
        file_id="file", document_type="supplier_quotation", purpose="quotation_extraction",
        request_id="request", content=b"fixture", mime_type="application/pdf",
    )).source == "mock"
    migration = (Path(__file__).resolve().parents[1] / "alembic" / "versions" / "20260717_0007_document_intelligence_demo_contract.py").read_text(encoding="utf-8")
    assert 'revision = "20260717_0007"' in migration
    assert 'down_revision = "20260716_0006"' in migration
    assert all(name in migration for name in ("files", "ocr_jobs", "ai_jobs", "review_candidates", "steven_quote_import_candidates"))


def test_sanitizer_does_not_include_evidence_or_request_identifier():
    request = AiStructuringRequest(
        document_type="supplier_quotation", purpose="quotation_extraction", schema_name="steven.s2.quotation",
        schema_version="1.0", request_id="sensitive-trace-id", sanitized_text="demo@example.test 6123-4567",
        evidence=[EvidenceLocation(field_path="x", page=1, original_text="not forwarded", bbox=[0, 0, 1, 1], confidence=1)],
    )
    payload = build_sanitized_ai_input(request)
    assert "sensitive-trace-id" not in payload and "not forwarded" not in payload
    assert "demo@example.test" not in payload and "6123-4567" not in payload


def test_sanitized_fixture_manifest_ground_truth_and_demo_policy_contract():
    implementation_root = Path(__file__).resolve().parents[3]
    fixture_root = implementation_root / "demo-data" / "steven-d0"
    manifest = json.loads((fixture_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["contains_real_data"] is False
    assert manifest["normal_baseline"] == "3 suppliers x 5 items = 15 offer lines"
    assert len(manifest["artifacts"]) == 6

    normal_candidates = []
    for artifact in manifest["artifacts"]:
        assert (fixture_root / artifact["file"]).is_file()
        truth = json.loads((fixture_root / artifact["ground_truth"]).read_text(encoding="utf-8"))
        assert truth["classification"] == "fully_sanitized_demo_data"
        validate_structured_candidate("steven.s2.quotation", truth["candidate"])
        if truth["expected_result"] == "needs_review_then_confirmable":
            normal_candidates.append(truth["candidate"])
    assert {entry["supplier_code"] for entry in normal_candidates} == {"SUP-A", "SUP-B", "SUP-C"}
    assert all(entry["currency"] == "HKD" and len(entry["items"]) == 5 for entry in normal_candidates)

    policy = json.loads((implementation_root / "config" / "demo-policy.json").read_text(encoding="utf-8"))
    assert policy["required_quote_count"] == {
        "value": 3,
        "status": "demo_assumption",
        "note": "仅用于脱敏演示，不代表香港学校法定或校方正式采购要求。",
    }
    assert all(policy[field]["status"] == "pending_client_confirmation" for field in (
        "purchase_amount_thresholds",
        "approval_levels",
        "record_retention_period",
    ))
