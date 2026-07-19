from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from threading import RLock
from typing import Iterator

from app.modules.document_intelligence.schemas import DocumentFile, ProcessingJob, ReviewCandidate


class InMemoryDocumentIntelligenceRepository:
    def __init__(self) -> None:
        self._files: dict[str, DocumentFile] = {}
        self._ocr_jobs: dict[str, ProcessingJob] = {}
        self._ai_jobs: dict[str, ProcessingJob] = {}
        self._candidates: dict[str, ReviewCandidate] = {}
        self._lock = RLock()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._lock:
            snapshot = deepcopy((self._files, self._ocr_jobs, self._ai_jobs, self._candidates))
            try:
                yield
            except Exception:
                self._files, self._ocr_jobs, self._ai_jobs, self._candidates = snapshot
                raise

    def add_file(self, record: DocumentFile) -> DocumentFile:
        with self._lock:
            self._files[record.id] = record.model_copy(deep=True)
            return record.model_copy(deep=True)

    def get_file(self, file_id: str) -> DocumentFile | None:
        with self._lock:
            record = self._files.get(file_id)
            return record.model_copy(deep=True) if record else None

    def list_candidates_for_target(self, target_object_id: str) -> list[ReviewCandidate]:
        with self._lock:
            return [
                candidate.model_copy(deep=True)
                for candidate in self._candidates.values()
                if candidate.target_object_id == target_object_id
            ]

    def add_ocr_job(self, job: ProcessingJob) -> ProcessingJob:
        with self._lock:
            self._ocr_jobs[job.id] = job.model_copy(deep=True)
            return job.model_copy(deep=True)

    def add_ai_job(self, job: ProcessingJob) -> ProcessingJob:
        with self._lock:
            self._ai_jobs[job.id] = job.model_copy(deep=True)
            return job.model_copy(deep=True)

    def save_ocr_job(self, job: ProcessingJob) -> ProcessingJob:
        with self._lock:
            self._ocr_jobs[job.id] = job.model_copy(deep=True)
            return job.model_copy(deep=True)

    def save_ai_job(self, job: ProcessingJob) -> ProcessingJob:
        with self._lock:
            self._ai_jobs[job.id] = job.model_copy(deep=True)
            return job.model_copy(deep=True)

    def get_job(self, job_id: str) -> ProcessingJob | None:
        with self._lock:
            job = self._ocr_jobs.get(job_id) or self._ai_jobs.get(job_id)
            return job.model_copy(deep=True) if job else None

    def add_candidate(self, candidate: ReviewCandidate) -> ReviewCandidate:
        with self._lock:
            self._candidates[candidate.id] = candidate.model_copy(deep=True)
            return candidate.model_copy(deep=True)

    def get_candidate(self, candidate_id: str) -> ReviewCandidate | None:
        with self._lock:
            candidate = self._candidates.get(candidate_id)
            return candidate.model_copy(deep=True) if candidate else None

    def save_candidate(self, candidate: ReviewCandidate) -> ReviewCandidate:
        with self._lock:
            if candidate.id not in self._candidates:
                raise ValueError("candidate_not_found")
            self._candidates[candidate.id] = deepcopy(candidate)
            return candidate.model_copy(deep=True)

    def add_s2_link(self, candidate_id: str, quote_id: str) -> None:
        candidate = self._candidates.get(candidate_id)
        if candidate is None or candidate.target_object_id != quote_id:
            raise ValueError("candidate_link_mismatch")

    def add_s1_link(self, candidate_id: str, tender_id: str) -> None:
        candidate = self._candidates.get(candidate_id)
        if candidate is None or candidate.target_object_id != tender_id:
            raise ValueError("candidate_link_mismatch")

    def has_s2_link(self, candidate_id: str, quote_id: str) -> bool:
        candidate = self._candidates.get(candidate_id)
        return bool(candidate and candidate.target_object_type == "steven_quote_job" and candidate.target_object_id == quote_id)

    def has_s1_link(self, candidate_id: str, tender_id: str) -> bool:
        candidate = self._candidates.get(candidate_id)
        return bool(candidate and candidate.target_object_type == "steven_tender_job" and candidate.target_object_id == tender_id)
