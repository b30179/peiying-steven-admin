from __future__ import annotations

from app.core.api_response import ApiError
from app.modules.document_intelligence.adapters import AiStructuringAdapter, OcrAdapter, validate_structured_candidate
from app.modules.document_intelligence.repository import InMemoryDocumentIntelligenceRepository
from app.modules.document_intelligence.storage import DocumentFileStorage
from app.modules.document_intelligence.schemas import (
    AiStructuringRequest,
    CandidateRevisionRequest,
    DocumentFile,
    OcrRequest,
    ProcessingJob,
    ReviewCandidate,
    ScanImportCreateRequest,
    TenderScanImportCreateRequest,
)
import hashlib


def transition_candidate_jobs(repository, candidate: ReviewCandidate, target: str) -> None:
    for job_id, saver in (
        (candidate.ocr_job_id, repository.save_ocr_job),
        (candidate.ai_job_id, repository.save_ai_job),
    ):
        if not job_id:
            continue
        job = repository.get_job(job_id)
        if job is not None and job.status == "needs_review":
            job.transition(target)
            saver(job)


class DocumentIntelligenceService:
    def __init__(self, repository: InMemoryDocumentIntelligenceRepository, storage: DocumentFileStorage, ocr: OcrAdapter, ai: AiStructuringAdapter) -> None:
        self.repository = repository
        self.storage = storage
        self.ocr = ocr
        self.ai = ai

    def store_file(self, *, filename: str, content: bytes, mime_type: str, document_type: str, purpose: str, actor: str, request_id: str) -> DocumentFile:
        digest = hashlib.sha256(content).hexdigest()
        record = DocumentFile(
            document_type=document_type,
            purpose=purpose,
            original_filename=filename,
            storage_key=f"demo-documents/{digest[:2]}/{digest}",
            mime_type=mime_type,
            size_bytes=len(content),
            sha256=digest,
            created_by=actor,
            request_id=request_id,
        )
        self.storage.put(record.storage_key, content, record.sha256)
        return self.repository.add_file(record)

    def create_scan_candidate(self, payload: ScanImportCreateRequest | TenderScanImportCreateRequest, content: bytes, mime_type: str, request_id: str) -> ReviewCandidate:
        candidate = ReviewCandidate(
            source_file_id=payload.source_file_id,
            document_type=payload.document_type,
            purpose=payload.purpose,
            schema_name=payload.schema_name,
            schema_version=payload.schema_version,
            provider="pending",
            model="pending",
            target_object_type=payload.target_object_type,
            target_object_id=payload.target_object_id,
            request_id=request_id,
        )
        candidate = self.repository.add_candidate(candidate)
        candidate.transition("running")
        self.repository.save_candidate(candidate)
        ocr_job = self.repository.add_ocr_job(ProcessingJob(
            file_id=payload.source_file_id,
            document_type=payload.document_type,
            purpose=payload.purpose,
            provider=type(self.ocr).__name__,
            model="configured-server-side",
            status="running",
            request_id=request_id,
        ))
        candidate.ocr_job_id = ocr_job.id
        self.repository.save_candidate(candidate)
        try:
            ocr_result = self.ocr.extract(OcrRequest(
                file_id=payload.source_file_id,
                document_type=payload.document_type,
                purpose=payload.purpose,
                request_id=request_id,
                content=content,
                mime_type=mime_type,
            ))
            ocr_job.provider = ocr_result.provider
            ocr_job.model = ocr_result.model
            ocr_job.transition("needs_review", output={"text": ocr_result.text, "warnings": ocr_result.warnings, "source": ocr_result.source})
            self.repository.save_ocr_job(ocr_job)
            ai_job = self.repository.add_ai_job(ProcessingJob(
                file_id=payload.source_file_id,
                document_type=payload.document_type,
                purpose=payload.purpose,
                provider=type(self.ai).__name__,
                model="configured-server-side",
                status="running",
                request_id=request_id,
            ))
            candidate.ai_job_id = ai_job.id
            self.repository.save_candidate(candidate)
            try:
                ai_result = self.ai.structure(AiStructuringRequest(
                    document_type=payload.document_type,
                    purpose=payload.purpose,
                    schema_name=payload.schema_name,
                    schema_version=payload.schema_version,
                    request_id=request_id,
                    sanitized_text=ocr_result.text,
                    evidence=ocr_result.evidence,
                ))
            except Exception as error:
                ai_job.transition("failed", error_code=type(error).__name__)
                self.repository.save_ai_job(ai_job)
                raise
            ai_job.provider = ai_result.provider
            ai_job.model = ai_result.model
            ai_job.transition("needs_review", output={"candidate": ai_result.candidate, "warnings": ai_result.warnings, "source": ai_result.source})
            self.repository.save_ai_job(ai_job)
            candidate.provider = f"{ocr_result.provider}+{ai_result.provider}"
            candidate.model = f"{ocr_result.model}+{ai_result.model}"
            candidate.candidate_json = ai_result.candidate
            candidate.warnings = [*ocr_result.warnings, *ai_result.warnings]
            candidate.evidence = ocr_result.evidence
            candidate.transition("needs_review")
            return self.repository.save_candidate(candidate)
        except Exception as error:
            if ocr_job.status == "running":
                ocr_job.transition("failed", error_code=type(error).__name__)
                self.repository.save_ocr_job(ocr_job)
            if candidate.status == "running":
                candidate.transition("failed")
                candidate.warnings = ["provider_processing_failed"]
                self.repository.save_candidate(candidate)
            raise

    def create_scan_candidate_for_file(self, payload: ScanImportCreateRequest | TenderScanImportCreateRequest, request_id: str) -> ReviewCandidate:
        record = self.repository.get_file(payload.source_file_id)
        content = self.storage.read(record.storage_key) if record else None
        if not record or content is None:
            raise ApiError(404, "source_file_not_found", "未找到扫描导入源文件。")
        return self.create_scan_candidate(payload, content, record.mime_type, request_id)

    def get_job(self, job_id: str) -> ProcessingJob:
        job = self.repository.get_job(job_id)
        if not job:
            raise ApiError(404, "document_job_not_found", "未找到文档处理任务。")
        return job

    def get_candidate(self, candidate_id: str) -> ReviewCandidate:
        candidate = self.repository.get_candidate(candidate_id)
        if not candidate:
            raise ApiError(404, "candidate_not_found", "未找到扫描导入候选。")
        return candidate

    def get_file(self, file_id: str) -> DocumentFile:
        record = self.repository.get_file(file_id)
        if not record:
            raise ApiError(404, "source_file_not_found", "未找到扫描导入源文件。")
        return record

    def read_file(self, file_id: str) -> tuple[DocumentFile, bytes]:
        record = self.get_file(file_id)
        content = self.storage.read(record.storage_key)
        if content is None:
            raise ApiError(404, "source_file_content_not_found", "源文件内容不可用。")
        return record, content

    def list_candidates(self, target_object_id: str) -> list[ReviewCandidate]:
        return self.repository.list_candidates_for_target(target_object_id)

    def get_quote_candidate(self, candidate_id: str, quote_id: str) -> ReviewCandidate:
        candidate = self.get_candidate(candidate_id)
        if (
            candidate.target_object_type != "steven_quote_job"
            or candidate.target_object_id != quote_id
            or candidate.schema_name != "steven.s2.quotation"
            or candidate.purpose != "quotation_extraction"
            or not self.repository.has_s2_link(candidate_id, quote_id)
        ):
            raise ApiError(404, "candidate_not_found", "未找到当前采购事项的扫描候选。")
        return candidate

    def revise_quote_candidate(self, candidate_id: str, quote_id: str, payload: CandidateRevisionRequest, reviewer_id: str) -> ReviewCandidate:
        self.get_quote_candidate(candidate_id, quote_id)
        return self.revise_candidate(candidate_id, payload, reviewer_id)

    def reject_quote_candidate(self, candidate_id: str, quote_id: str, reviewer_id: str) -> ReviewCandidate:
        self.get_quote_candidate(candidate_id, quote_id)
        return self.reject_candidate(candidate_id, reviewer_id)

    def get_tender_candidate(self, candidate_id: str, tender_id: str) -> ReviewCandidate:
        candidate = self.get_candidate(candidate_id)
        if (
            candidate.target_object_type != "steven_tender_job"
            or candidate.target_object_id != tender_id
            or candidate.schema_name != "steven.s1.tender_source"
            or candidate.purpose != "tender_source_extraction"
            or not self.repository.has_s1_link(candidate_id, tender_id)
        ):
            raise ApiError(404, "candidate_not_found", "未找到当前文书事项的扫描候选。")
        return candidate

    def revise_tender_candidate(self, candidate_id: str, tender_id: str, payload: CandidateRevisionRequest, reviewer_id: str) -> ReviewCandidate:
        self.get_tender_candidate(candidate_id, tender_id)
        return self.revise_candidate(candidate_id, payload, reviewer_id)

    def reject_tender_candidate(self, candidate_id: str, tender_id: str, reviewer_id: str) -> ReviewCandidate:
        self.get_tender_candidate(candidate_id, tender_id)
        return self.reject_candidate(candidate_id, reviewer_id)

    def revise_candidate(self, candidate_id: str, payload: CandidateRevisionRequest, reviewer_id: str) -> ReviewCandidate:
        candidate = self.get_candidate(candidate_id)
        if candidate.status != "needs_review":
            raise ApiError(409, "candidate_not_reviewable", "候选当前不可修改。")
        candidate.human_revision_json = validate_structured_candidate(candidate.schema_name, payload.revision)
        candidate.reviewer_id = reviewer_id
        return self.repository.save_candidate(candidate)

    def reject_candidate(self, candidate_id: str, reviewer_id: str) -> ReviewCandidate:
        candidate = self.get_candidate(candidate_id)
        try:
            candidate.transition("rejected", reviewer_id)
        except ValueError as error:
            raise ApiError(409, str(error), "候选状态不允许拒绝。") from error
        transition_candidate_jobs(self.repository, candidate, "rejected")
        return self.repository.save_candidate(candidate)

    def mark_confirmed(self, candidate_id: str, reviewer_id: str) -> ReviewCandidate:
        candidate = self.get_candidate(candidate_id)
        try:
            candidate.transition("confirmed", reviewer_id)
        except ValueError as error:
            raise ApiError(409, str(error), "候选状态不允许确认。") from error
        transition_candidate_jobs(self.repository, candidate, "confirmed")
        return self.repository.save_candidate(candidate)
