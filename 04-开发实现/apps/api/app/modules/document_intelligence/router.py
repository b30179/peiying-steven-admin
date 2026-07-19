from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile, status

from app.core.api_response import ApiError, request_id_for, success
from app.core.auth import Actor, current_principal
from app.core.permissions import QUOTES_IMPORT, QUOTES_READ, TENDERS_READ, TENDERS_WRITE
from app.modules.document_intelligence.schemas import CandidateRevisionRequest, ScanCandidateConfirmRequest, ScanImportCreateRequest
from app.modules.steven.quote_permissions import require_quote_importer, require_quote_reader

router = APIRouter(prefix="/api/v1/steven", tags=["steven-document-intelligence"])
documents_router = APIRouter(prefix="/api/v1/documents", tags=["document-upload"])

_UPLOAD_PURPOSES = {
    "quotation_extraction": {
        "document_type": "supplier_quotation",
        "permission": QUOTES_IMPORT,
    },
    "tender_source_extraction": {
        "document_type": "tender_source",
        "permission": TENDERS_WRITE,
    },
}
_MIME_BY_SUFFIX = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
_READ_PERMISSION_BY_PURPOSE = {
    "quotation_extraction": QUOTES_READ,
    "tender_source_extraction": TENDERS_READ,
}
_MAGIC_BY_MIME = {
    "application/pdf": (b"%PDF-",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
}


def _documents(request: Request):
    service = getattr(request.app.state, "document_intelligence", None)
    if service is None:
        raise ApiError(503, "document_intelligence_unavailable", "文档智能底座尚未配置。")
    return service


def _ensure_demo_enabled(request: Request) -> None:
    settings = request.app.state.settings
    if not settings.demo_profile_enabled or not settings.ocr_enabled or not settings.ai_structuring_enabled:
        raise ApiError(409, "document_intelligence_disabled", "受控 OCR/AI 文档处理当前已关闭。")


def _require_upload_permission(request: Request, actor: Actor, permission: str) -> None:
    if permission in actor.permissions:
        return
    request.app.state.auth_repository.record_security_event(
        "auth.authorization_rejected",
        "rejected",
        actor.user_id,
        actor.user_id,
        {"missing_permissions": [permission], "method": request.method, "path": request.url.path},
    )
    raise ApiError(403, "forbidden", "当前账户无权执行此操作。", {"missing_permissions": [permission]})


def _validated_upload(file: UploadFile, content: bytes) -> tuple[str, str]:
    if not content:
        raise ApiError(422, "empty_file", "上传文件不能为空。")
    if len(content) > 10 * 1024 * 1024:
        raise ApiError(413, "file_too_large", "扫描导入文件不得超过 10 MB。")
    filename = Path(file.filename or "sanitized-demo-document").name
    suffix = Path(filename).suffix.casefold()
    expected_mime = _MIME_BY_SUFFIX.get(suffix)
    if expected_mime is None:
        raise ApiError(415, "unsupported_document_type", "仅接受 PDF、PNG 或 JPEG 脱敏文件。")
    supplied_mime = (file.content_type or "").casefold()
    if supplied_mime not in {expected_mime, "application/octet-stream"}:
        raise ApiError(415, "unsupported_document_type", "文件扩展名与 MIME 类型不一致。")
    if not any(content.startswith(signature) for signature in _MAGIC_BY_MIME[expected_mime]):
        raise ApiError(415, "document_signature_mismatch", "文件内容签名与扩展名不一致。")
    return filename, expected_mime



def _require_document_read_permission(request: Request, actor: Actor, purpose: str) -> None:
    permission = _READ_PERMISSION_BY_PURPOSE.get(purpose)
    if permission is None:
        raise ApiError(403, "document_scope_forbidden", "当前文档用途不允许通过此接口读取。")
    _require_upload_permission(request, actor, permission)


def _require_legacy_s2_candidate(request: Request, candidate_id: str, quote_id: str | None = None):
    candidate = _documents(request).get_candidate(candidate_id)
    if (
        candidate.target_object_type != "steven_quote_job"
        or candidate.schema_name != "steven.s2.quotation"
        or candidate.purpose != "quotation_extraction"
        or (quote_id is not None and candidate.target_object_id != quote_id)
    ):
        raise ApiError(404, "candidate_not_found", "未找到采购报价扫描候选。")
    return candidate

def _audit(request: Request, actor: str, action: str, object_type: str, object_id: str, before_after: dict) -> None:
    request.app.state.audit_repository.append(
        actor=actor,
        action=action,
        object_type=object_type,
        object_id=object_id,
        before_after=before_after,
        request_id=request_id_for(request),
    )


@documents_router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_shared_document(
    request: Request,
    file: UploadFile = File(),
    document_type: str = Form(),
    purpose: str = Form(),
    actor: Actor = Depends(current_principal),
) -> dict:
    _ensure_demo_enabled(request)
    policy = _UPLOAD_PURPOSES.get(purpose)
    if policy is None or document_type != policy["document_type"]:
        raise ApiError(422, "unsupported_document_purpose", "文档类型与受控处理用途不匹配。")
    _require_upload_permission(request, actor, policy["permission"])
    content = await file.read()
    filename, mime_type = _validated_upload(file, content)
    record = _documents(request).store_file(
        filename=filename,
        content=content,
        mime_type=mime_type,
        document_type=document_type,
        purpose=purpose,
        actor=actor.actor_id,
        request_id=request_id_for(request),
    )
    _audit(request, actor.actor_id, "document.file_uploaded", "file", record.id, {
        "after": {
            "sha256": record.sha256,
            "size_bytes": record.size_bytes,
            "document_type": record.document_type,
            "purpose": record.purpose,
            "is_demo": record.is_demo,
        }
    })
    return success(request, record.model_dump(mode="json"))


@router.post("/files", status_code=status.HTTP_201_CREATED)
async def upload_document_file(
    request: Request,
    file: UploadFile = File(),
    actor: Actor = Depends(require_quote_importer),
) -> dict:
    _ensure_demo_enabled(request)
    content = await file.read()
    filename, mime_type = _validated_upload(file, content)
    record = _documents(request).store_file(
        filename=filename,
        content=content,
        mime_type=mime_type,
        document_type="supplier_quotation",
        purpose="quotation_extraction",
        actor=actor.actor_id,
        request_id=request_id_for(request),
    )
    _audit(request, actor.actor_id, "document.file_uploaded", "file", record.id, {"after": {"sha256": record.sha256, "size_bytes": record.size_bytes, "is_demo": record.is_demo}})
    return success(request, record.model_dump(mode="json"))


@router.get("/files/{file_id}/content")
async def read_document_file(request: Request, file_id: str, actor: Actor = Depends(current_principal)) -> Response:
    record, content = _documents(request).read_file(file_id)
    _require_document_read_permission(request, actor, record.purpose)
    return Response(content=content, media_type=record.mime_type)


@router.post("/scan-imports", status_code=status.HTTP_201_CREATED)
async def create_scan_import(
    request: Request,
    payload: ScanImportCreateRequest,
    actor: Actor = Depends(require_quote_importer),
) -> dict:
    _ensure_demo_enabled(request)
    candidate = _documents(request).create_scan_candidate_for_file(payload, request_id_for(request))
    _audit(request, actor.actor_id, "document.candidate_created", "review_candidate", candidate.id, {"after": {"status": candidate.status, "quote_id": payload.quote_id, "source_file_id": payload.source_file_id}})
    return success(request, candidate.model_dump(mode="json"))


@router.get("/document-jobs/{job_id}")
async def get_document_job(request: Request, job_id: str, actor: Actor = Depends(current_principal)) -> dict:
    job = _documents(request).get_job(job_id)
    _require_document_read_permission(request, actor, job.purpose)
    return success(request, job.model_dump(mode="json"))


@router.get("/review-candidates")
async def list_review_candidates(request: Request, quote_id: str, _: Actor = Depends(require_quote_reader)) -> dict:
    records = [
        item.model_dump(mode="json")
        for item in _documents(request).list_candidates(quote_id)
        if item.target_object_type == "steven_quote_job"
        and item.schema_name == "steven.s2.quotation"
        and item.purpose == "quotation_extraction"
    ]
    return success(request, records, {"page": 1, "page_size": len(records), "total": len(records)})


@router.get("/review-candidates/{candidate_id}")
async def get_review_candidate(request: Request, candidate_id: str, _: Actor = Depends(require_quote_reader)) -> dict:
    return success(request, _require_legacy_s2_candidate(request, candidate_id).model_dump(mode="json"))


@router.patch("/review-candidates/{candidate_id}")
async def revise_review_candidate(
    request: Request,
    candidate_id: str,
    payload: CandidateRevisionRequest,
    actor: Actor = Depends(require_quote_importer),
) -> dict:
    _require_legacy_s2_candidate(request, candidate_id)
    candidate = _documents(request).revise_candidate(candidate_id, payload, actor.actor_id)
    _audit(request, actor.actor_id, "document.candidate_revised", "review_candidate", candidate.id, {"after": {"status": candidate.status, "human_revision_present": True}})
    return success(request, candidate.model_dump(mode="json"))


@router.post("/review-candidates/{candidate_id}/confirm")
async def confirm_review_candidate(
    request: Request,
    candidate_id: str,
    payload: ScanCandidateConfirmRequest,
    actor: Actor = Depends(require_quote_importer),
) -> dict:
    application = getattr(request.app.state, "scan_import_application", None)
    if application is None:
        raise ApiError(503, "scan_confirmation_unavailable", "扫描候选确认事务尚未配置。")
    _require_legacy_s2_candidate(request, candidate_id, payload.quote_id)
    quote = application.confirm_scan_candidate(candidate_id, payload.quote_id, actor.actor_id)
    return success(request, quote.model_dump(mode="json"))


@router.post("/review-candidates/{candidate_id}/reject")
async def reject_review_candidate(
    request: Request,
    candidate_id: str,
    actor: Actor = Depends(require_quote_importer),
) -> dict:
    _require_legacy_s2_candidate(request, candidate_id)
    candidate = _documents(request).reject_candidate(candidate_id, actor.actor_id)
    _audit(request, actor.actor_id, "document.candidate_rejected", "review_candidate", candidate.id, {"before": {"status": "needs_review"}, "after": {"status": "rejected"}})
    return success(request, candidate.model_dump(mode="json"))
