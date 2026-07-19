from __future__ import annotations

from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse

from app.core.api_response import ApiError, success
from app.core.auth import Actor
from app.modules.document_intelligence.schemas import (
    CandidateRevisionRequest,
    SourceFileScanRequest,
    TenderScanImportCreateRequest,
)
from app.modules.steven.tender_permissions import (
    require_tender_approver,
    require_tender_audit_reader,
    require_tender_exporter,
    require_tender_reader,
    require_tender_proofreader,
    require_tender_submitter,
    require_tender_writer,
)
from app.modules.steven.tender_schemas import (
    TenderBatchExportRequest,
    TenderCreateRequest,
    TenderDecisionRequest,
    TenderProofreadingApplyRequest,
    TenderProofreadingReviewRequest,
    TenderScanConfirmRequest,
    TenderTemplateCreateRequest,
    TenderTemplatePreviewRequest,
    TenderTemplateUpdateRequest,
    TenderUpdateRequest,
)

tenders_router = APIRouter(prefix="/api/v1/steven", tags=["steven-tenders"])


def tender_application(request: Request):
    return request.app.state.tender_application


def tender_proofreading_service(request: Request):
    service = getattr(request.app.state, "tender_proofreading_service", None)
    if service is None:
        raise ApiError(503, "proofreading_unavailable", "AI 校對只在 PostgreSQL 執行模式下提供。")
    return service


def tender_scan_application(request: Request):
    service = getattr(request.app.state, "tender_scan_application", None)
    if service is None:
        raise ApiError(503, "tender_scan_confirmation_unavailable", "文書扫描候选确认事务尚未配置。")
    return service


def document_intelligence(request: Request):
    service = getattr(request.app.state, "document_intelligence", None)
    if service is None:
        raise ApiError(503, "document_intelligence_unavailable", "文档处理服务尚未配置。")
    return service


def content_disposition(filename: str) -> str:
    return f"attachment; filename=tender.docx; filename*=UTF-8''{quote(filename, safe='')}"


@tenders_router.get("/tender-templates")
async def list_tender_templates(request: Request, _: Actor = Depends(require_tender_reader)) -> dict:
    records = [item.model_dump(mode="json") for item in tender_application(request).list_templates()]
    return success(request, records, {"page": 1, "page_size": len(records), "total": len(records)})


@tenders_router.get("/tenders/templates/recommend")
async def recommend_tender_templates(
    request: Request,
    q: str = Query(min_length=1, max_length=250),
    _: Actor = Depends(require_tender_reader),
) -> dict:
    records = [item.model_dump(mode="json") for item in tender_application(request).recommend_templates(q)]
    return success(request, records, {"page": 1, "page_size": len(records), "total": len(records)})


@tenders_router.post("/tenders/templates", status_code=status.HTTP_201_CREATED)
async def create_tender_template(
    request: Request,
    payload: TenderTemplateCreateRequest,
    actor: Actor = Depends(require_tender_writer),
) -> dict:
    return success(request, tender_application(request).create_template(payload, actor.actor_id).model_dump(mode="json"))


@tenders_router.put("/tenders/templates/{template_id}")
async def update_tender_template(
    request: Request,
    template_id: str,
    payload: TenderTemplateUpdateRequest,
    actor: Actor = Depends(require_tender_writer),
) -> dict:
    return success(request, tender_application(request).update_template(template_id, payload, actor.actor_id).model_dump(mode="json"))


@tenders_router.delete("/tenders/templates/{template_id}")
async def delete_tender_template(
    request: Request,
    template_id: str,
    actor: Actor = Depends(require_tender_writer),
) -> dict:
    return success(request, tender_application(request).delete_template(template_id, actor.actor_id))


@tenders_router.get("/tender-templates/{template_id}/preview")
async def preview_tender_template(
    request: Request,
    template_id: str,
    tender_id: str | None = None,
    _: Actor = Depends(require_tender_reader),
) -> dict:
    return success(request, tender_application(request).preview_template(template_id, tender_id))


@tenders_router.post("/tender-templates/{template_id}/preview")
async def preview_tender_template_draft(
    request: Request,
    template_id: str,
    payload: TenderTemplatePreviewRequest,
    tender_id: str | None = None,
    _: Actor = Depends(require_tender_reader),
) -> dict:
    return success(request, tender_application(request).preview_template(template_id, tender_id, payload))


@tenders_router.get("/tenders")
async def list_tenders(request: Request, _: Actor = Depends(require_tender_reader)) -> dict:
    records = [item.model_dump(mode="json") for item in tender_application(request).list_tenders()]
    return success(request, records, {"page": 1, "page_size": len(records), "total": len(records)})


@tenders_router.post("/tenders", status_code=status.HTTP_201_CREATED)
async def create_tender(request: Request, payload: TenderCreateRequest, actor: Actor = Depends(require_tender_writer)) -> dict:
    return success(request, tender_application(request).create_tender(payload, actor.actor_id).model_dump(mode="json"))


@tenders_router.get("/tenders/{tender_id}")
async def get_tender(request: Request, tender_id: str, _: Actor = Depends(require_tender_reader)) -> dict:
    return success(request, tender_application(request).get_tender(tender_id).model_dump(mode="json"))


@tenders_router.delete("/tenders/{tender_id}")
async def delete_tender(
    request: Request,
    tender_id: str,
    actor: Actor = Depends(require_tender_writer),
) -> dict:
    return success(request, tender_application(request).delete_tender(tender_id, actor.actor_id))


@tenders_router.get("/tenders/{tender_id}/print-summary", response_class=HTMLResponse)
async def print_tender_summary(
    request: Request,
    tender_id: str,
    _: Actor = Depends(require_tender_exporter),
) -> HTMLResponse:
    return HTMLResponse(
        content=tender_application(request).print_summary(tender_id),
        headers={"Cache-Control": "no-store"},
    )


@tenders_router.patch("/tenders/{tender_id}")
async def update_tender(
    request: Request,
    tender_id: str,
    payload: TenderUpdateRequest,
    actor: Actor = Depends(require_tender_writer),
) -> dict:
    return success(request, tender_application(request).update_tender(tender_id, payload, actor.actor_id).model_dump(mode="json"))


@tenders_router.post("/tenders/{tender_id}/preview")
async def preview_tender(request: Request, tender_id: str, actor: Actor = Depends(require_tender_writer)) -> dict:
    return success(request, tender_application(request).preview(tender_id, actor.actor_id).model_dump(mode="json"))


@tenders_router.get("/tenders/{tender_id}/draft.docx")
async def download_tender_draft(request: Request, tender_id: str, actor: Actor = Depends(require_tender_writer)) -> StreamingResponse:
    filename, content = tender_application(request).draft_bytes(tender_id, actor.actor_id)
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": content_disposition(filename)},
    )


@tenders_router.post("/tenders/{tender_id}/scan", status_code=status.HTTP_201_CREATED)
async def scan_tender_source(
    request: Request,
    tender_id: str,
    payload: SourceFileScanRequest,
    actor: Actor = Depends(require_tender_writer),
) -> dict:
    tender = tender_application(request).get_tender(tender_id)
    if tender.status not in {"draft", "draft_error", "returned"}:
        raise ApiError(409, "tender_not_editable", "当前状态不可扫描导入文书。", {"status": tender.status})
    candidate = document_intelligence(request).create_scan_candidate_for_file(
        TenderScanImportCreateRequest(tender_id=tender_id, source_file_id=payload.source_file_id),
        request.state.request_id,
    )
    request.app.state.audit_repository.append(
        actor=actor.actor_id,
        action="tender.scan_candidate_created",
        object_type="steven_tender_job",
        object_id=tender_id,
        request_id=request.state.request_id,
        before_after={"before": None, "after": {"candidate_id": candidate.id, "status": candidate.status}},
    )
    return success(request, candidate.model_dump(mode="json"))


@tenders_router.get("/tenders/{tender_id}/scan-candidates")
async def list_tender_scan_candidates(
    request: Request, tender_id: str, _: Actor = Depends(require_tender_reader)
) -> dict:
    service = document_intelligence(request)
    records = []
    for item in service.list_candidates(tender_id):
        try:
            service.get_tender_candidate(item.id, tender_id)
        except ApiError:
            continue
        records.append(item.model_dump(mode="json"))
    return success(request, records, {"page": 1, "page_size": len(records), "total": len(records)})


@tenders_router.patch("/tenders/{tender_id}/scan-candidates/{candidate_id}")
async def revise_tender_scan_candidate(
    request: Request,
    tender_id: str,
    candidate_id: str,
    payload: CandidateRevisionRequest,
    actor: Actor = Depends(require_tender_writer),
) -> dict:
    revised = document_intelligence(request).revise_tender_candidate(
        candidate_id, tender_id, payload, actor.actor_id
    )
    return success(request, revised.model_dump(mode="json"))


@tenders_router.post("/tenders/{tender_id}/scan-candidates/{candidate_id}/confirm")
async def confirm_tender_scan_candidate(
    request: Request,
    tender_id: str,
    candidate_id: str,
    payload: TenderScanConfirmRequest | None = None,
    actor: Actor = Depends(require_tender_writer),
) -> dict:
    result = tender_scan_application(request).confirm_scan_candidate(
        candidate_id, tender_id, actor.actor_id, request.state.request_id, payload.template_id if payload else None
    )
    try:
        proofreading = tender_proofreading_service(request).start(
            tender_id, actor.actor_id, request.state.request_id
        )
        result["proofreading"] = {"status": "needs_review", "candidate": proofreading}
    except ApiError as error:
        result["proofreading"] = {"status": "failed", "error_code": error.code}
    except Exception as error:
        result["proofreading"] = {"status": "failed", "error_code": type(error).__name__[:100]}
    return success(request, result)


@tenders_router.post("/tenders/{tender_id}/scan-candidates/{candidate_id}/reject")
async def reject_tender_scan_candidate(
    request: Request,
    tender_id: str,
    candidate_id: str,
    actor: Actor = Depends(require_tender_writer),
) -> dict:
    rejected = document_intelligence(request).reject_tender_candidate(
        candidate_id, tender_id, actor.actor_id
    )
    return success(request, rejected.model_dump(mode="json"))


@tenders_router.post("/tenders/{tender_id}/proofreading", status_code=status.HTTP_201_CREATED)
async def start_tender_proofreading(request: Request, tender_id: str, actor: Actor = Depends(require_tender_proofreader)) -> dict:
    result = tender_proofreading_service(request).start(tender_id, actor.actor_id, request.state.request_id)
    return success(request, result)


@tenders_router.get("/tenders/{tender_id}/proofreading")
async def list_tender_proofreading(request: Request, tender_id: str, _: Actor = Depends(require_tender_reader)) -> dict:
    records = tender_proofreading_service(request).list(tender_id)
    return success(request, records, {"page": 1, "page_size": len(records), "total": len(records)})


@tenders_router.get("/tenders/{tender_id}/proofreading/{candidate_id}")
async def get_tender_proofreading(request: Request, tender_id: str, candidate_id: str, _: Actor = Depends(require_tender_reader)) -> dict:
    return success(request, tender_proofreading_service(request).get(tender_id, candidate_id))


@tenders_router.patch("/tenders/{tender_id}/proofreading/{candidate_id}/review")
async def review_tender_proofreading(request: Request, tender_id: str, candidate_id: str, payload: TenderProofreadingReviewRequest, actor: Actor = Depends(require_tender_proofreader)) -> dict:
    result = tender_proofreading_service(request).review(tender_id, candidate_id, payload.decisions, actor.actor_id, request.state.request_id)
    return success(request, result)


@tenders_router.post("/tenders/{tender_id}/proofreading/{candidate_id}/issues/{issue_id}/apply")
async def apply_tender_proofreading_issue(
    request: Request,
    tender_id: str,
    candidate_id: str,
    issue_id: str,
    payload: TenderProofreadingApplyRequest,
    actor: Actor = Depends(require_tender_proofreader),
) -> dict:
    candidate = tender_proofreading_service(request).apply_issue(
        tender_id,
        candidate_id,
        issue_id,
        payload.replacement_text,
        actor.actor_id,
        request.state.request_id,
    )
    tender = tender_application(request).get_tender(tender_id).model_dump(mode="json")
    return success(request, {"candidate": candidate, "tender": tender})


@tenders_router.post("/tenders/{tender_id}/proofreading/{candidate_id}/confirm")
async def confirm_tender_proofreading(request: Request, tender_id: str, candidate_id: str, actor: Actor = Depends(require_tender_proofreader)) -> dict:
    result = tender_proofreading_service(request).confirm(tender_id, candidate_id, actor.actor_id, request.state.request_id)
    return success(request, result)


@tenders_router.post("/tenders/{tender_id}/submit")
async def submit_tender(request: Request, tender_id: str, actor: Actor = Depends(require_tender_submitter)) -> dict:
    return success(request, tender_application(request).submit(tender_id, actor.actor_id).model_dump(mode="json"))


@tenders_router.post("/tenders/{tender_id}/approve")
async def approve_tender(
    request: Request,
    tender_id: str,
    payload: TenderDecisionRequest,
    actor: Actor = Depends(require_tender_approver),
) -> dict:
    return success(request, tender_application(request).approve(tender_id, actor.actor_id, payload.opinion).model_dump(mode="json"))


@tenders_router.post("/tenders/{tender_id}/return")
async def return_tender(
    request: Request,
    tender_id: str,
    payload: TenderDecisionRequest,
    actor: Actor = Depends(require_tender_approver),
) -> dict:
    return success(request, tender_application(request).return_for_revision(tender_id, actor.actor_id, payload.opinion).model_dump(mode="json"))


@tenders_router.post("/tenders/{tender_id}/export")
async def export_tender(request: Request, tender_id: str, actor: Actor = Depends(require_tender_exporter)) -> dict:
    return success(request, tender_application(request).export(tender_id, actor.actor_id).model_dump(mode="json"))


@tenders_router.post("/tenders/{tender_id}/batch-export")
async def batch_export_tender(
    request: Request,
    tender_id: str,
    payload: TenderBatchExportRequest,
    actor: Actor = Depends(require_tender_exporter),
) -> dict:
    result = tender_application(request).batch_export(tender_id, payload.supplier_ids, actor.actor_id)
    return success(request, result.model_dump(mode="json"))


@tenders_router.get("/tenders/{tender_id}/versions")
async def list_tender_versions(request: Request, tender_id: str, _: Actor = Depends(require_tender_reader)) -> dict:
    records = [item.model_dump(mode="json") for item in tender_application(request).list_versions(tender_id)]
    return success(request, records, {"page": 1, "page_size": len(records), "total": len(records)})


@tenders_router.post("/tenders/{tender_id}/versions/{version_id}/reconcile")
async def reconcile_tender_version(
    request: Request,
    tender_id: str,
    version_id: str,
    actor: Actor = Depends(require_tender_exporter),
) -> dict:
    result = tender_application(request).reconcile_export(tender_id, version_id, actor.actor_id)
    return success(request, result.model_dump(mode="json"))


@tenders_router.get("/tenders/{tender_id}/versions/{version_number}/download")
async def download_tender_version(
    request: Request,
    tender_id: str,
    version_number: int,
    _: Actor = Depends(require_tender_exporter),
) -> FileResponse:
    path = tender_application(request).version_file(tender_id, version_number)
    return FileResponse(
        path=path,
        filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@tenders_router.get("/tenders/{tender_id}/audit-events")
async def list_tender_audit_events(
    request: Request,
    tender_id: str,
    _: Actor = Depends(require_tender_audit_reader),
) -> dict:
    records = tender_application(request).list_audit_events(tender_id)
    return success(request, records, {"page": 1, "page_size": len(records), "total": len(records)})
