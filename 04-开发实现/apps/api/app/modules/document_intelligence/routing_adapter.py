from __future__ import annotations

from app.modules.document_intelligence.schemas import AiStructuringRequest, AiStructuringResult


class RoutingAiStructuringAdapter:
    def __init__(self, adapters: dict[str, object]) -> None:
        self.adapters = adapters

    def structure(self, request: AiStructuringRequest) -> AiStructuringResult:
        adapter = self.adapters.get(request.schema_name)
        if adapter is None:
            raise ValueError("schema_adapter_not_enabled")
        return adapter.structure(request)


class DisabledOcrAdapter:
    def extract(self, request):
        raise RuntimeError("ocr_processing_disabled")


class DisabledAiStructuringAdapter:
    def structure(self, request):
        raise RuntimeError("ai_structuring_disabled")
