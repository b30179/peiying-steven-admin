from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Connection, text

from app.modules.document_intelligence.schemas import DocumentFile, EvidenceLocation, ProcessingJob, ReviewCandidate


class PostgresDocumentIntelligenceRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def add_file(self, record: DocumentFile) -> DocumentFile:
        self.connection.execute(text("""
            INSERT INTO files
                (id,module,document_type,purpose,original_filename,storage_key,mime_type,size_bytes,sha256,status,is_demo,created_by,request_id,created_at)
            VALUES
                (:id,:module,:document_type,:purpose,:original_filename,:storage_key,:mime_type,:size_bytes,:sha256,:status,:is_demo,:created_by,:request_id,:created_at)
        """), record.model_dump(mode="python"))
        return record

    def get_file(self, file_id: str) -> DocumentFile | None:
        row = self.connection.execute(text("SELECT * FROM files WHERE id=:id"), {"id": file_id}).mappings().first()
        return DocumentFile.model_validate(dict(row)) if row else None

    def list_candidates_for_target(self, target_object_id: str) -> list[ReviewCandidate]:
        rows = self.connection.execute(
            text("SELECT * FROM review_candidates WHERE target_object_id=:target_object_id ORDER BY created_at DESC"),
            {"target_object_id": target_object_id},
        ).mappings().all()
        return [ReviewCandidate.model_validate(dict(row)) for row in rows]

    def add_ocr_job(self, job: ProcessingJob) -> ProcessingJob:
        return self._add_job("ocr_jobs", job)

    def add_ai_job(self, job: ProcessingJob) -> ProcessingJob:
        return self._add_job("ai_jobs", job)

    def _add_job(self, table: str, job: ProcessingJob) -> ProcessingJob:
        values = job.model_dump(mode="json")
        values["output_json"] = json.dumps(values["output_json"], ensure_ascii=False)
        self.connection.execute(text(f"""
            INSERT INTO {table}
                (id,file_id,module,document_type,purpose,provider,model,status,request_id,output_json,error_code,created_at,updated_at)
            VALUES
                (:id,:file_id,:module,:document_type,:purpose,:provider,:model,:status,:request_id,CAST(:output_json AS jsonb),:error_code,:created_at,:updated_at)
        """), values)
        return job

    def save_ocr_job(self, job: ProcessingJob) -> ProcessingJob:
        return self._save_job("ocr_jobs", job)

    def save_ai_job(self, job: ProcessingJob) -> ProcessingJob:
        return self._save_job("ai_jobs", job)

    def _save_job(self, table: str, job: ProcessingJob) -> ProcessingJob:
        values = job.model_dump(mode="json")
        values["output_json"] = json.dumps(values["output_json"], ensure_ascii=False)
        self.connection.execute(text(f"""
            UPDATE {table} SET provider=:provider,model=:model,status=:status,
                output_json=CAST(:output_json AS jsonb),error_code=:error_code,updated_at=:updated_at
            WHERE id=:id
        """), values)
        return job

    def get_job(self, job_id: str) -> ProcessingJob | None:
        for table in ("ocr_jobs", "ai_jobs"):
            row = self.connection.execute(text(f"SELECT * FROM {table} WHERE id=:id"), {"id": job_id}).mappings().first()
            if row:
                return ProcessingJob.model_validate(dict(row))
        return None

    def add_candidate(self, candidate: ReviewCandidate) -> ReviewCandidate:
        values = candidate.model_dump(mode="json")
        values["candidate_json"] = json.dumps(values["candidate_json"], ensure_ascii=False)
        values["human_revision_json"] = json.dumps(values["human_revision_json"], ensure_ascii=False) if values["human_revision_json"] is not None else None
        values["warnings"] = json.dumps(values["warnings"], ensure_ascii=False)
        values["evidence"] = json.dumps(values["evidence"], ensure_ascii=False)
        self.connection.execute(text("""
            INSERT INTO review_candidates
                (id,source_file_id,ocr_job_id,ai_job_id,module,document_type,purpose,schema_name,schema_version,provider,model,status,
                 candidate_json,human_revision_json,warnings,evidence,reviewer_id,target_object_type,target_object_id,request_id,created_at,updated_at,reviewed_at)
            VALUES
                (:id,:source_file_id,:ocr_job_id,:ai_job_id,:module,:document_type,:purpose,:schema_name,:schema_version,:provider,:model,:status,
                 CAST(:candidate_json AS jsonb),CAST(COALESCE(:human_revision_json, 'null') AS jsonb),CAST(:warnings AS jsonb),CAST(:evidence AS jsonb),:reviewer_id,
                 :target_object_type,:target_object_id,:request_id,:created_at,:updated_at,:reviewed_at)
        """), values)
        return candidate

    def get_candidate(self, candidate_id: str) -> ReviewCandidate | None:
        row = self.connection.execute(text("SELECT * FROM review_candidates WHERE id=:id"), {"id": candidate_id}).mappings().first()
        if not row:
            return None
        values = dict(row)
        values["evidence"] = [EvidenceLocation.model_validate(item) for item in values["evidence"]]
        return ReviewCandidate.model_validate(values)

    def save_candidate(self, candidate: ReviewCandidate) -> ReviewCandidate:
        values = candidate.model_dump(mode="json")
        for key in ("candidate_json", "human_revision_json", "warnings", "evidence"):
            values[key] = json.dumps(values[key], ensure_ascii=False) if values[key] is not None else None
        result = self.connection.execute(text("""
            UPDATE review_candidates SET
                status=:status,candidate_json=CAST(:candidate_json AS jsonb),human_revision_json=CAST(:human_revision_json AS jsonb),
                warnings=CAST(:warnings AS jsonb),evidence=CAST(:evidence AS jsonb),reviewer_id=:reviewer_id,
                updated_at=:updated_at,reviewed_at=:reviewed_at
            WHERE id=:id
        """), values)
        if result.rowcount != 1:
            raise ValueError("candidate_not_found")
        return candidate

    def add_s2_link(self, candidate_id: str, quote_id: str) -> None:
        self.connection.execute(text("""
            INSERT INTO steven_quote_import_candidates (candidate_id,quote_job_id,created_at)
            VALUES (:candidate_id,:quote_id,now())
            ON CONFLICT (candidate_id) DO NOTHING
        """), {"candidate_id": candidate_id, "quote_id": quote_id})

    def add_s1_link(self, candidate_id: str, tender_id: str) -> None:
        self.connection.execute(text("""
            INSERT INTO steven_tender_candidate_links
                (candidate_id,tender_job_id,candidate_kind,created_at)
            VALUES (:candidate_id,:tender_id,'tender_source_extraction',now())
            ON CONFLICT (candidate_id) DO NOTHING
        """), {"candidate_id": candidate_id, "tender_id": tender_id})

    def has_s2_link(self, candidate_id: str, quote_id: str) -> bool:
        return bool(self.connection.execute(text("""
            SELECT 1 FROM steven_quote_import_candidates
            WHERE candidate_id=:candidate_id AND quote_job_id=:quote_id
        """), {"candidate_id": candidate_id, "quote_id": quote_id}).scalar_one_or_none())

    def has_s1_link(self, candidate_id: str, tender_id: str) -> bool:
        return bool(self.connection.execute(text("""
            SELECT 1 FROM steven_tender_candidate_links
            WHERE candidate_id=:candidate_id AND tender_job_id=:tender_id
              AND candidate_kind='tender_source_extraction'
        """), {"candidate_id": candidate_id, "tender_id": tender_id}).scalar_one_or_none())

    def lock_candidate(self, candidate_id: str) -> None:
        self.connection.execute(text("SELECT id FROM review_candidates WHERE id=:id FOR UPDATE"), {"id": candidate_id})
