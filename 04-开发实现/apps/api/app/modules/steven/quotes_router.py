from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse

from app.core.api_response import ApiError, success
from app.core.auth import Actor
from app.modules.document_intelligence.schemas import CandidateRevisionRequest, ScanImportCreateRequest, SourceFileScanRequest
from app.modules.steven.quote_permissions import (
    require_quote_approver,
    require_quote_audit_reader,
    require_quote_exporter,
    require_quote_importer,
    require_quote_reader,
    require_quote_recommender,
    require_quote_submitter,
    require_quote_writer,
)
from app.modules.steven.quote_schemas import (
    QuoteApprovalRequest,
    QuoteCreateRequest,
    QuoteImportConfirmRequest,
    QuoteInquiryDraftRequest,
    QuoteItemCreateRequest,
    QuoteOfferLineCreateRequest,
    QuoteRecommendationRequest,
    QuoteSupplierCreateRequest,
    QuoteSupplierReuseRequest,
)

quotes_router = APIRouter(prefix="/api/v1/steven", tags=["steven-quotes"])


def quote_service(request: Request):
    return request.app.state.quote_application


def ai_assist_service(request: Request):
    service = getattr(request.app.state, "ai_assist_service", None)
    if service is None:
        raise ApiError(503, "ai_assist_unavailable", "AI 增强服务尚未配置。")
    return service



def quote_scan_candidate(request: Request, quote_id: str, candidate_id: str):
    quote_service(request).get_quote(quote_id)
    documents = getattr(request.app.state, "document_intelligence", None)
    if documents is None:
        raise ApiError(503, "document_intelligence_unavailable", "文档处理服务尚未配置。")
    return documents.get_quote_candidate(candidate_id, quote_id)

@quotes_router.get("/quotes")
async def list_quotes(request: Request, _: Actor = Depends(require_quote_reader)) -> dict:
    records = [record.model_dump(mode="json") for record in quote_service(request).list_quotes()]
    return success(request, records, {"page": 1, "page_size": len(records), "total": len(records)})


@quotes_router.get("/quotes/suppliers/search")
async def search_quote_suppliers(
    request: Request,
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=20, ge=1, le=100),
    _: Actor = Depends(require_quote_reader),
) -> dict:
    records = [item.model_dump(mode="json") for item in quote_service(request).search_suppliers(q, limit)]
    return success(request, records, {"page": 1, "page_size": len(records), "total": len(records)})


@quotes_router.post("/quotes/inquiry-draft")
async def create_quote_inquiry_draft(
    request: Request,
    payload: QuoteInquiryDraftRequest,
    _: Actor = Depends(require_quote_reader),
) -> dict:
    result = ai_assist_service(request).inquiry_draft(payload.supplier_name, payload.items, payload.purpose)
    return success(request, result.model_dump(mode="json"))


@quotes_router.post("/quotes", status_code=status.HTTP_201_CREATED)
async def create_quote(
    request: Request,
    payload: QuoteCreateRequest,
    actor: Actor = Depends(require_quote_writer),
) -> dict:
    return success(request, quote_service(request).create_quote(payload, actor.actor_id).model_dump(mode="json"))


@quotes_router.get("/quotes/{quote_id}")
async def get_quote(request: Request, quote_id: str, _: Actor = Depends(require_quote_reader)) -> dict:
    return success(request, quote_service(request).get_quote(quote_id).model_dump(mode="json"))


@quotes_router.delete("/quotes/{quote_id}")
async def delete_quote(
    request: Request,
    quote_id: str,
    actor: Actor = Depends(require_quote_writer),
) -> dict:
    return success(request, quote_service(request).delete_quote(quote_id, actor.actor_id))


@quotes_router.post("/quotes/{quote_id}/items")
async def add_quote_item(
    request: Request,
    quote_id: str,
    payload: QuoteItemCreateRequest,
    actor: Actor = Depends(require_quote_writer),
) -> dict:
    return success(request, quote_service(request).add_item(quote_id, payload, actor.actor_id).model_dump(mode="json"))


@quotes_router.post("/quotes/{quote_id}/suppliers")
async def add_quote_supplier(
    request: Request,
    quote_id: str,
    payload: QuoteSupplierCreateRequest,
    actor: Actor = Depends(require_quote_writer),
) -> dict:
    return success(request, quote_service(request).add_supplier(quote_id, payload, actor.actor_id).model_dump(mode="json"))


@quotes_router.post("/quotes/{quote_id}/reuse-supplier")
async def reuse_quote_supplier(
    request: Request,
    quote_id: str,
    payload: QuoteSupplierReuseRequest,
    actor: Actor = Depends(require_quote_writer),
) -> dict:
    return success(request, quote_service(request).reuse_supplier(quote_id, payload, actor.actor_id).model_dump(mode="json"))


@quotes_router.post("/quotes/{quote_id}/offer-lines")
async def add_quote_offer_line(
    request: Request,
    quote_id: str,
    payload: QuoteOfferLineCreateRequest,
    actor: Actor = Depends(require_quote_writer),
) -> dict:
    return success(request, quote_service(request).add_offer(quote_id, payload, actor.actor_id).model_dump(mode="json"))


@quotes_router.post("/quotes/{quote_id}/scan", status_code=status.HTTP_201_CREATED)
async def scan_supplier_quotation(
    request: Request,
    quote_id: str,
    payload: SourceFileScanRequest,
    actor: Actor = Depends(require_quote_importer),
) -> dict:
    quote_service(request).get_quote(quote_id)
    documents = getattr(request.app.state, "document_intelligence", None)
    if documents is None:
        from app.core.api_response import ApiError

        raise ApiError(503, "document_intelligence_unavailable", "文档处理服务尚未配置。")
    candidate = documents.create_scan_candidate_for_file(
        ScanImportCreateRequest(quote_id=quote_id, source_file_id=payload.source_file_id),
        request.state.request_id,
    )
    request.app.state.audit_repository.append(
        actor=actor.actor_id,
        action="quote.scan_candidate_created",
        object_type="steven_quote_job",
        object_id=quote_id,
        request_id=request.state.request_id,
        before_after={"before": None, "after": {"candidate_id": candidate.id, "status": candidate.status}},
    )
    return success(request, candidate.model_dump(mode="json"))



@quotes_router.get("/quotes/{quote_id}/scan-candidates/{candidate_id}")
async def get_quote_scan_candidate(
    request: Request, quote_id: str, candidate_id: str, _: Actor = Depends(require_quote_reader)
) -> dict:
    candidate = quote_scan_candidate(request, quote_id, candidate_id)
    return success(request, candidate.model_dump(mode="json"))


@quotes_router.patch("/quotes/{quote_id}/scan-candidates/{candidate_id}")
async def revise_quote_scan_candidate(
    request: Request,
    quote_id: str,
    candidate_id: str,
    payload: CandidateRevisionRequest,
    actor: Actor = Depends(require_quote_importer),
) -> dict:
    quote_scan_candidate(request, quote_id, candidate_id)
    candidate = request.app.state.document_intelligence.revise_quote_candidate(
        candidate_id, quote_id, payload, actor.actor_id
    )
    request.app.state.audit_repository.append(
        actor=actor.actor_id,
        action="quote.scan_candidate_revised",
        object_type="steven_quote_job",
        object_id=quote_id,
        request_id=request.state.request_id,
        before_after={"after": {"candidate_id": candidate.id, "human_revision_present": True}},
    )
    return success(request, candidate.model_dump(mode="json"))


@quotes_router.post("/quotes/{quote_id}/scan-candidates/{candidate_id}/confirm")
async def confirm_quote_scan_candidate(
    request: Request, quote_id: str, candidate_id: str, actor: Actor = Depends(require_quote_importer)
) -> dict:
    quote_scan_candidate(request, quote_id, candidate_id)
    application = getattr(request.app.state, "scan_import_application", None)
    if application is None:
        raise ApiError(503, "scan_confirmation_unavailable", "扫描候选确认事务尚未配置。")
    quote = application.confirm_scan_candidate(candidate_id, quote_id, actor.actor_id)
    return success(request, quote.model_dump(mode="json"))


@quotes_router.post("/quotes/{quote_id}/scan-candidates/{candidate_id}/reject")
async def reject_quote_scan_candidate(
    request: Request, quote_id: str, candidate_id: str, actor: Actor = Depends(require_quote_importer)
) -> dict:
    quote_scan_candidate(request, quote_id, candidate_id)
    candidate = request.app.state.document_intelligence.reject_quote_candidate(
        candidate_id, quote_id, actor.actor_id
    )
    request.app.state.audit_repository.append(
        actor=actor.actor_id,
        action="quote.scan_candidate_rejected",
        object_type="steven_quote_job",
        object_id=quote_id,
        request_id=request.state.request_id,
        before_after={"before": {"status": "needs_review"}, "after": {"candidate_id": candidate.id, "status": "rejected"}},
    )
    return success(request, candidate.model_dump(mode="json"))


@quotes_router.get("/quotes/{quote_id}/scan-candidates/{candidate_id}/source")
async def read_quote_scan_source(
    request: Request, quote_id: str, candidate_id: str, _: Actor = Depends(require_quote_reader)
) -> Response:
    candidate = quote_scan_candidate(request, quote_id, candidate_id)
    record, content = request.app.state.document_intelligence.read_file(candidate.source_file_id)
    if record.purpose != "quotation_extraction" or record.document_type != "supplier_quotation":
        raise ApiError(404, "source_file_not_found", "未找到当前采购事项的扫描源文件。")
    return Response(content=content, media_type=record.mime_type)

@quotes_router.post("/quotes/import")
async def precheck_quote_import(
    request: Request,
    quote_id: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    actor: Actor = Depends(require_quote_importer),
) -> dict:
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        from app.core.api_response import ApiError

        raise ApiError(413, "file_too_large", "导入文件不得超过 5 MB。")
    preview = quote_service(request).precheck_import(
        quote_id=quote_id,
        filename=file.filename or "upload.xlsx",
        content=content,
        actor=actor.actor_id,
    )
    return success(request, preview.model_dump(mode="json"))


@quotes_router.post("/quotes/{quote_id}/confirm-import")
async def confirm_quote_import(
    request: Request,
    quote_id: str,
    payload: QuoteImportConfirmRequest,
    actor: Actor = Depends(require_quote_importer),
) -> dict:
    return success(request, quote_service(request).confirm_import(quote_id, payload.batch_id, actor.actor_id).model_dump(mode="json"))


@quotes_router.post("/quotes/{quote_id}/recommendation")
async def save_quote_recommendation(
    request: Request,
    quote_id: str,
    payload: QuoteRecommendationRequest,
    actor: Actor = Depends(require_quote_recommender),
) -> dict:
    return success(request, quote_service(request).save_recommendation(quote_id, payload, actor.actor_id).model_dump(mode="json"))


@quotes_router.post("/quotes/{quote_id}/ai-recommend")
async def recommend_quote_supplier(
    request: Request,
    quote_id: str,
    _: Actor = Depends(require_quote_recommender),
) -> dict:
    return success(request, quote_service(request).recommend_supplier(quote_id, ai_assist_service(request)))


@quotes_router.post("/quotes/{quote_id}/submit-approval")
async def submit_quote_approval(
    request: Request,
    quote_id: str,
    actor: Actor = Depends(require_quote_submitter),
) -> dict:
    return success(request, quote_service(request).submit_approval(quote_id, actor.actor_id).model_dump(mode="json"))


@quotes_router.post("/quotes/{quote_id}/approve")
async def approve_quote(
    request: Request,
    quote_id: str,
    payload: QuoteApprovalRequest,
    actor: Actor = Depends(require_quote_approver),
) -> dict:
    return success(request, quote_service(request).approve(quote_id, actor.actor_id, payload.opinion).model_dump(mode="json"))


@quotes_router.post("/quotes/{quote_id}/reject")
async def reject_quote(
    request: Request,
    quote_id: str,
    payload: QuoteApprovalRequest,
    actor: Actor = Depends(require_quote_approver),
) -> dict:
    return success(request, quote_service(request).reject(quote_id, actor.actor_id, payload.opinion).model_dump(mode="json"))


@quotes_router.post("/quotes/{quote_id}/export")
async def export_quote(
    request: Request,
    quote_id: str,
    actor: Actor = Depends(require_quote_exporter),
) -> dict:
    return success(request, quote_service(request).export(quote_id, actor.actor_id).model_dump(mode="json"))


@quotes_router.get("/quotes/{quote_id}/audit-events")
async def list_quote_audit_events(
    request: Request, quote_id: str, _: Actor = Depends(require_quote_audit_reader)
) -> dict:
    records = quote_service(request).list_audit_events(quote_id)
    return success(request, records, {"page": 1, "page_size": len(records), "total": len(records)})


@quotes_router.get("/quotes/{quote_id}/versions")
async def list_quote_versions(request: Request, quote_id: str, _: Actor = Depends(require_quote_reader)) -> dict:
    versions = [version.model_dump(mode="json") for version in quote_service(request).list_versions(quote_id)]
    return success(request, versions, {"page": 1, "page_size": len(versions), "total": len(versions)})


@quotes_router.get("/quotes/{quote_id}/versions/{version_number}/download")
async def download_quote_version(
    request: Request,
    quote_id: str,
    version_number: int,
    _: Actor = Depends(require_quote_exporter),
) -> FileResponse:
    path = quote_service(request).version_file(quote_id, version_number)
    return FileResponse(path=path, filename=path.name, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
