from __future__ import annotations

from sqlalchemy import Engine

from app.core.api_response import ApiError
from app.modules.document_intelligence.postgres_repository import PostgresDocumentIntelligenceRepository
from app.modules.document_intelligence.schemas import (
    AiStructuringRequest,
    OcrRequest,
    ProcessingJob,
    ReviewCandidate,
)
from app.modules.document_intelligence.service import DocumentIntelligenceService


class PostgresDocumentIntelligenceService:
    def __init__(self, engine: Engine, storage, ocr, ai) -> None:
        self.engine = engine
        self.storage = storage
        self.ocr = ocr
        self.ai = ai

    def _run(self, method: str, *args, **kwargs):
        with self.engine.begin() as connection:
            service = DocumentIntelligenceService(PostgresDocumentIntelligenceRepository(connection), self.storage, self.ocr, self.ai)
            return getattr(service, method)(*args, **kwargs)

    def store_file(self, **kwargs):
        return self._run("store_file", **kwargs)

    def create_scan_candidate_for_file(self, payload, request_id: str):
        with self.engine.begin() as connection:
            repository = PostgresDocumentIntelligenceRepository(connection)
            record = repository.get_file(payload.source_file_id)
        if record is None:
            raise ApiError(404, "source_file_not_found", "未找到扫描导入源文件。")
        content = self.storage.read(record.storage_key)
        if content is None:
            raise ApiError(404, "source_file_content_not_found", "源文件内容不可用。")

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
        candidate.transition("running")
        ocr_job = ProcessingJob(
            file_id=payload.source_file_id,
            document_type=payload.document_type,
            purpose=payload.purpose,
            provider=type(self.ocr).__name__,
            model="configured-server-side",
            status="running",
            request_id=request_id,
        )
        with self.engine.begin() as connection:
            repository = PostgresDocumentIntelligenceRepository(connection)
            repository.add_candidate(candidate)
            repository.add_ocr_job(ocr_job)
            candidate.ocr_job_id = ocr_job.id
            repository.save_candidate(candidate)
            self._link_candidate(repository, candidate)

        try:
            ocr_result = self.ocr.extract(OcrRequest(
                file_id=payload.source_file_id,
                document_type=payload.document_type,
                purpose=payload.purpose,
                request_id=request_id,
                content=content,
                mime_type=record.mime_type,
            ))
        except Exception as error:
            self._persist_failure(candidate.id, ocr_job.id, None, error)
            raise

        ai_job = ProcessingJob(
            file_id=payload.source_file_id,
            document_type=payload.document_type,
            purpose=payload.purpose,
            provider=type(self.ai).__name__,
            model="configured-server-side",
            status="running",
            request_id=request_id,
        )
        with self.engine.begin() as connection:
            repository = PostgresDocumentIntelligenceRepository(connection)
            stored_ocr_job = repository.get_job(ocr_job.id)
            stored_candidate = repository.get_candidate(candidate.id)
            if stored_ocr_job is None or stored_candidate is None:
                raise ApiError(409, "document_job_state_lost", "文档处理状态不可用。")
            stored_ocr_job.provider = ocr_result.provider
            stored_ocr_job.model = ocr_result.model
            stored_ocr_job.transition("needs_review", output={
                "text_length": len(ocr_result.text),
                "evidence_count": len(ocr_result.evidence),
                "warnings": ocr_result.warnings,
                "source": ocr_result.source,
            })
            repository.save_ocr_job(stored_ocr_job)
            repository.add_ai_job(ai_job)
            stored_candidate.ai_job_id = ai_job.id
            repository.save_candidate(stored_candidate)

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
            self._persist_failure(candidate.id, None, ai_job.id, error)
            raise

        with self.engine.begin() as connection:
            repository = PostgresDocumentIntelligenceRepository(connection)
            stored_ai_job = repository.get_job(ai_job.id)
            stored_candidate = repository.get_candidate(candidate.id)
            if stored_ai_job is None or stored_candidate is None:
                raise ApiError(409, "document_job_state_lost", "文档处理状态不可用。")
            stored_ai_job.provider = ai_result.provider
            stored_ai_job.model = ai_result.model
            stored_ai_job.transition("needs_review", output={
                "schema_name": payload.schema_name,
                "warnings": ai_result.warnings,
                "source": ai_result.source,
            })
            repository.save_ai_job(stored_ai_job)
            stored_candidate.provider = f"{ocr_result.provider}+{ai_result.provider}"
            stored_candidate.model = f"{ocr_result.model}+{ai_result.model}"
            stored_candidate.candidate_json = ai_result.candidate
            stored_candidate.warnings = [*ocr_result.warnings, *ai_result.warnings]
            stored_candidate.evidence = ocr_result.evidence
            stored_candidate.transition("needs_review")
            return repository.save_candidate(stored_candidate)

    @staticmethod
    def _link_candidate(repository: PostgresDocumentIntelligenceRepository, candidate: ReviewCandidate) -> None:
        if candidate.target_object_type == "steven_quote_job" and candidate.target_object_id:
            repository.add_s2_link(candidate.id, candidate.target_object_id)
        elif candidate.target_object_type == "steven_tender_job" and candidate.target_object_id:
            repository.add_s1_link(candidate.id, candidate.target_object_id)

    def _persist_failure(self, candidate_id: str, ocr_job_id: str | None, ai_job_id: str | None, error: Exception) -> None:
        error_code = type(error).__name__[:100]
        with self.engine.begin() as connection:
            repository = PostgresDocumentIntelligenceRepository(connection)
            if ocr_job_id:
                job = repository.get_job(ocr_job_id)
                if job is not None and job.status == "running":
                    job.transition("failed", error_code=error_code)
                    repository.save_ocr_job(job)
            if ai_job_id:
                job = repository.get_job(ai_job_id)
                if job is not None and job.status == "running":
                    job.transition("failed", error_code=error_code)
                    repository.save_ai_job(job)
            candidate = repository.get_candidate(candidate_id)
            if candidate is not None and candidate.status == "running":
                candidate.transition("failed")
                candidate.warnings = ["provider_processing_failed"]
                repository.save_candidate(candidate)

    def get_job(self, job_id: str):
        return self._run("get_job", job_id)

    def get_candidate(self, candidate_id: str):
        return self._run("get_candidate", candidate_id)

    def get_file(self, file_id: str):
        return self._run("get_file", file_id)

    def read_file(self, file_id: str):
        return self._run("read_file", file_id)

    def list_candidates(self, target_object_id: str):
        return self._run("list_candidates", target_object_id)

    def get_quote_candidate(self, candidate_id: str, quote_id: str):
        return self._run("get_quote_candidate", candidate_id, quote_id)

    def revise_quote_candidate(self, candidate_id: str, quote_id: str, payload, reviewer_id: str):
        return self._run("revise_quote_candidate", candidate_id, quote_id, payload, reviewer_id)

    def reject_quote_candidate(self, candidate_id: str, quote_id: str, reviewer_id: str):
        return self._run("reject_quote_candidate", candidate_id, quote_id, reviewer_id)

    def get_tender_candidate(self, candidate_id: str, tender_id: str):
        return self._run("get_tender_candidate", candidate_id, tender_id)

    def revise_tender_candidate(self, candidate_id: str, tender_id: str, payload, reviewer_id: str):
        return self._run("revise_tender_candidate", candidate_id, tender_id, payload, reviewer_id)

    def reject_tender_candidate(self, candidate_id: str, tender_id: str, reviewer_id: str):
        return self._run("reject_tender_candidate", candidate_id, tender_id, reviewer_id)

    def revise_candidate(self, candidate_id: str, payload, reviewer_id: str):
        return self._run("revise_candidate", candidate_id, payload, reviewer_id)

    def reject_candidate(self, candidate_id: str, reviewer_id: str):
        return self._run("reject_candidate", candidate_id, reviewer_id)

    def mark_confirmed(self, candidate_id: str, reviewer_id: str):
        return self._run("mark_confirmed", candidate_id, reviewer_id)
