from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable, Protocol

import httpx
from pydantic import BaseModel

from app.modules.document_intelligence.schemas import (
    AiStructuringRequest,
    AiStructuringResult,
    EvidenceLocation,
    OcrRequest,
    OcrResult,
    QuotationExtractionCandidate,
    TenderSourceExtractionCandidate,
    TenderProofreadingCandidate,
)

FORBIDDEN_AI_FIELDS = {
    "recommended_supplier_id",
    "recommendation",
    "recommend",
    "ranking",
    "rank",
    "approval",
    "approve",
    "approved",
    "order",
    "total",
    "select_supplier",
}


class OcrAdapter(Protocol):
    def extract(self, request: OcrRequest) -> OcrResult: ...


class AiStructuringAdapter(Protocol):
    def structure(self, request: AiStructuringRequest) -> AiStructuringResult: ...


class MockOcrAdapter:
    def __init__(self, result: OcrResult | None = None) -> None:
        self._result = result

    def extract(self, request: OcrRequest) -> OcrResult:
        if self._result:
            return self._result
        return OcrResult(
            provider="mock",
            model="fixture-v1",
            text="脱敏演示报价。OCR/AI 提取结果必须人工确认。",
            evidence=[EvidenceLocation(field_path="document", page=1, original_text="脱敏演示报价", bbox=[0, 0, 100, 20], confidence=1)],
            source="mock",
        )


class MockAiStructuringAdapter:
    def __init__(self, candidate: dict[str, Any]) -> None:
        self._candidate = candidate

    def structure(self, request: AiStructuringRequest) -> AiStructuringResult:
        candidate = validate_structured_candidate(request.schema_name, self._candidate)
        return AiStructuringResult(provider="mock", model="fixture-v1", candidate=candidate, source="mock")


class MockTenderProofreadingAdapter:
    def structure(self, request: AiStructuringRequest) -> AiStructuringResult:
        match = re.search(r"DOCUMENT_SHA256:([a-f0-9]{64})", request.sanitized_text)
        if match is None:
            raise ValueError("proofreading_document_hash_missing")
        candidate = validate_structured_candidate(
            request.schema_name,
            {
                "document_sha256": match.group(1),
                "issues": [
                    {
                        "issue_id": "mock-terminology-001",
                        "category": "terminology_consistency",
                        "severity": "warning",
                        "field_path": "rendered_body",
                        "location": "文書正文",
                        "original_text": "Demo service",
                        "suggested_text": "示範服務（Demo service）",
                        "explanation": "中英文術語首次出現時建議並列，後續保持一致。",
                    }
                ],
                "summary": {"error": 0, "warning": 1, "info": 0, "total": 1},
            },
        )
        return AiStructuringResult(provider="mock", model="fixture-proofreading-v1", candidate=candidate, source="mock")


def httpx_json_transport(spec: dict[str, Any]) -> dict[str, Any]:
    timeout = httpx.Timeout(float(spec["timeout_seconds"]))
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        response = client.post(
            spec["url"],
            headers=spec.get("headers"),
            json=spec.get("json"),
            content=spec.get("content"),
        )
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("provider_response_not_object")
    return payload


class AzureDocumentIntelligenceAdapter:
    def __init__(self, endpoint: str, model: str, timeout_seconds: int, transport: Callable[[dict[str, Any]], dict[str, Any]], api_key: str | None = None) -> None:
        if not endpoint or not endpoint.startswith("https://"):
            raise ValueError("invalid_azure_endpoint")
        if model != "prebuilt-invoice":
            raise ValueError("unsupported_azure_model")
        if timeout_seconds <= 0:
            raise ValueError("invalid_timeout")
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._transport = transport
        self._api_key = api_key or os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY")

    def extract(self, request: OcrRequest) -> OcrResult:
        if not self._api_key:
            raise RuntimeError("azure_document_intelligence_secret_unavailable")
        response = self._transport({
            "url": f"{self.endpoint}/documentintelligence/documentModels/{self.model}:analyze?api-version=2024-11-30",
            "timeout_seconds": self.timeout_seconds,
            "headers": {"Ocp-Apim-Subscription-Key": self._api_key, "Content-Type": request.mime_type},
            "content": request.content,
        })
        return map_azure_invoice_response(response, self.model)


def map_azure_invoice_response(payload: dict[str, Any], model: str = "prebuilt-invoice") -> OcrResult:
    analyze = payload.get("analyzeResult", payload)
    lines: list[str] = []
    evidence: list[EvidenceLocation] = []
    for page_index, page in enumerate(analyze.get("pages", []), start=1):
        for line in page.get("lines", []):
            content = str(line.get("content", "")).strip()
            if not content:
                continue
            lines.append(content)
            polygon = [float(value) for point in line.get("polygon", []) for value in (point.values() if isinstance(point, dict) else [])]
            if not polygon:
                polygon = [float(value) for value in line.get("polygon", [0, 0, 0, 0])]
            evidence.append(EvidenceLocation(
                field_path="document.lines",
                page=int(page.get("pageNumber", page_index)),
                original_text=content,
                bbox=polygon[:8] if len(polygon) >= 4 else [0, 0, 0, 0],
                confidence=float(line.get("confidence", 0)),
            ))
    return OcrResult(provider="azure_document_intelligence", model=model, text="\n".join(lines), evidence=evidence, source="live")


class DeepSeekStructuringAdapter:
    def __init__(self, endpoint: str, model: str, timeout_seconds: int, transport: Callable[[dict[str, Any]], dict[str, Any]], api_key: str | None = None) -> None:
        if not endpoint or not endpoint.startswith("https://"):
            raise ValueError("invalid_deepseek_endpoint")
        if timeout_seconds <= 0:
            raise ValueError("invalid_timeout")
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._transport = transport
        self._api_key = api_key or load_deepseek_api_key()

    def structure(self, request: AiStructuringRequest) -> AiStructuringResult:
        if not self._api_key:
            raise RuntimeError("deepseek_secret_unavailable")
        body = {
            "model": self.model,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": build_system_prompt(request.schema_name)}, {"role": "user", "content": build_sanitized_ai_input(request)}],
        }
        response = self._transport({
            "url": f"{self.endpoint}/chat/completions",
            "timeout_seconds": self.timeout_seconds,
            "headers": {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
            "json": body,
        })
        content = response["choices"][0]["message"]["content"]
        candidate = validate_structured_candidate(request.schema_name, json.loads(content))
        return AiStructuringResult(provider="deepseek", model=self.model, candidate=candidate, source="live")


def load_deepseek_api_key() -> str | None:
    value = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if value:
        return value
    secret_path = Path(os.getenv("DEEPSEEK_API_KEY_FILE", r"D:\Yuki\memory\API Keys.md"))
    try:
        with secret_path.open("r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return None
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = stripped.casefold() == "## deepseek"
            continue
        if in_section:
            match = re.search(r"(?i)(?:api\s*)?key\*{0,2}\s*[:：]\s*`?([^`\s]+)`?", stripped)
            if match:
                return match.group(1).strip()
    return None


def build_system_prompt(schema_name: str) -> str:
    if schema_name == "steven.s1.tender_proofreading":
        prompt_path = Path(__file__).resolve().parents[1] / "steven" / "prompts" / "tender_proofreading.json"
        payload = json.loads(prompt_path.read_text(encoding="utf-8"))
        return json.dumps(payload, ensure_ascii=False)
    if schema_name == "steven.s2.quotation":
        prompt_path = Path(__file__).resolve().parents[1] / "steven" / "prompts" / "quotation_extraction.json"
        payload = json.loads(prompt_path.read_text(encoding="utf-8"))
        return json.dumps(payload, ensure_ascii=False)
    return "Extract only fields in the supplied schema. Never recommend, rank, approve, order, email, or calculate totals."

def build_sanitized_ai_input(request: AiStructuringRequest) -> str:
    sanitized = re.sub(r"[\w.+-]+@[\w.-]+", "[REDACTED_EMAIL]", request.sanitized_text)
    sanitized = re.sub(r"(?<!\d)(?:\+?852[- ]?)?[2569]\d{3}[- ]?\d{4}(?!\d)", "[REDACTED_PHONE]", sanitized)
    return json.dumps({
        "module": request.module,
        "document_type": request.document_type,
        "purpose": request.purpose,
        "schema_name": request.schema_name,
        "schema_version": request.schema_version,
        "sanitized_text": sanitized,
    }, ensure_ascii=False)


def _reject_forbidden_fields(value: Any, forbidden_fields: set[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in forbidden_fields:
                raise ValueError("forbidden_ai_decision_field")
            _reject_forbidden_fields(child, forbidden_fields)
    elif isinstance(value, list):
        for child in value:
            _reject_forbidden_fields(child, forbidden_fields)


def validate_structured_candidate(schema_name: str, candidate: dict[str, Any]) -> dict[str, Any]:
    forbidden_fields = FORBIDDEN_AI_FIELDS if schema_name == "steven.s2.quotation" else FORBIDDEN_AI_FIELDS - {"total"}
    _reject_forbidden_fields(candidate, forbidden_fields)
    if schema_name == "steven.s2.quotation" and "quotes" not in candidate:
        candidate = {"quotes": [candidate]}
    schemas: dict[str, type[BaseModel]] = {
        "steven.s2.quotation": QuotationExtractionCandidate,
        "steven.s1.tender_source": TenderSourceExtractionCandidate,
        "steven.s1.tender_proofreading": TenderProofreadingCandidate,
    }
    schema = schemas.get(schema_name)
    if schema is None:
        raise ValueError("schema_not_enabled")
    return schema.model_validate(candidate).model_dump(mode="json")
