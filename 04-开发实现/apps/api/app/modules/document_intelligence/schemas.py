from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

JobStatus = Literal["pending", "running", "needs_review", "confirmed", "rejected", "failed"]
DocumentModule = Literal["steven"]
DocumentPurpose = Literal[
    "quotation_extraction",
    "quote_exception_explanation",
    "tender_source_extraction",
    "clause_draft",
    "tender_proofreading",
    "inventory_sheet_extraction",
    "inventory_exception_explanation",
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EvidenceLocation(BaseModel):
    field_path: str = Field(min_length=1, max_length=300)
    page: int = Field(ge=1)
    original_text: str = Field(min_length=1, max_length=4000)
    bbox: list[float] = Field(min_length=4, max_length=8)
    confidence: float = Field(ge=0, le=1)


class OcrRequest(BaseModel):
    file_id: str
    module: DocumentModule = "steven"
    document_type: str = Field(min_length=1, max_length=100)
    purpose: DocumentPurpose
    request_id: str
    content: bytes = Field(repr=False)
    mime_type: str


class OcrResult(BaseModel):
    provider: str
    model: str
    text: str
    evidence: list[EvidenceLocation]
    warnings: list[str] = Field(default_factory=list)
    source: Literal["mock", "cached_demo", "live"] = "mock"


class AiStructuringRequest(BaseModel):
    module: DocumentModule = "steven"
    document_type: str
    purpose: DocumentPurpose
    schema_name: str
    schema_version: str
    request_id: str
    sanitized_text: str = Field(max_length=50_000)
    evidence: list[EvidenceLocation] = Field(max_length=100)


class AiStructuringResult(BaseModel):
    provider: str
    model: str
    candidate: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)
    source: Literal["mock", "cached_demo", "live"] = "mock"


class QuotationItemCandidate(BaseModel):
    item_code: str = Field(min_length=1, max_length=50)
    item: str = Field(min_length=1, max_length=200)
    specification: str = Field(default="", max_length=500)
    qty: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    unit: str = Field(min_length=1, max_length=30)
    unit_price: Decimal = Field(ge=0, max_digits=14, decimal_places=2)


class QuotationSupplierCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_code: str = Field(min_length=1, max_length=50)
    supplier_name: str = Field(min_length=1, max_length=200)
    quote_date: str | None = None
    currency: str = Field(min_length=3, max_length=3)
    valid_until: str | None = None
    freight: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    tax: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    items: list[QuotationItemCandidate] = Field(min_length=1)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("quote_date", "valid_until")
    @classmethod
    def normalize_optional_date(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized or normalized == "REVIEW-PLACEHOLDER":
            return None
        date.fromisoformat(normalized)
        return normalized


class QuotationExtractionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quotes: list[QuotationSupplierCandidate] = Field(min_length=1, max_length=20)


class TenderSourceExtractionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=250)
    document_number: str | None = Field(default=None, max_length=100)
    subject: str | None = Field(default=None, max_length=250)
    generated_date: str | None = None
    deadline_date: str | None = None
    budget_min: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    budget_max: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    location: str | None = Field(default=None, max_length=300)
    supplier_names: list[str] = Field(default_factory=list, max_length=20)
    controlled_clauses: str | None = Field(default=None, max_length=10000)
    uncertain_fields: list[str] = Field(default_factory=list, max_length=30)


class TenderProofreadingIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issue_id: str = Field(min_length=1, max_length=100)
    category: Literal[
        "terminology_consistency",
        "number_date_currency_format",
        "grammar_fluency",
        "unresolved_variable",
    ]
    severity: Literal["error", "warning", "info"]
    field_path: str = Field(min_length=1, max_length=300)
    location: str = Field(min_length=1, max_length=500)
    original_text: str = Field(min_length=1, max_length=2000)
    suggested_text: str = Field(default="", max_length=2000)
    explanation: str = Field(min_length=1, max_length=2000)


class TenderProofreadingCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    issues: list[TenderProofreadingIssue] = Field(default_factory=list, max_length=200)
    summary: dict[str, int]

    @model_validator(mode="after")
    def validate_summary_and_ids(self):
        issue_ids = [issue.issue_id for issue in self.issues]
        if len(issue_ids) != len(set(issue_ids)):
            raise ValueError("duplicate_issue_id")
        expected = {
            "error": sum(issue.severity == "error" for issue in self.issues),
            "warning": sum(issue.severity == "warning" for issue in self.issues),
            "info": sum(issue.severity == "info" for issue in self.issues),
            "total": len(self.issues),
        }
        if self.summary != expected:
            raise ValueError("invalid_proofreading_summary")
        return self

class ReviewCandidate(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    source_file_id: str
    module: DocumentModule = "steven"
    document_type: str
    purpose: DocumentPurpose
    schema_name: str
    schema_version: str
    provider: str
    model: str
    status: JobStatus = "pending"
    candidate_json: dict[str, Any] = Field(default_factory=dict)
    human_revision_json: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    evidence: list[EvidenceLocation] = Field(default_factory=list)
    reviewer_id: str | None = None
    target_object_type: str | None = None
    target_object_id: str | None = None
    request_id: str
    ocr_job_id: str | None = None
    ai_job_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    reviewed_at: datetime | None = None

    def transition(self, target: JobStatus, reviewer_id: str | None = None) -> None:
        allowed = {
            "pending": {"running", "failed"},
            "running": {"needs_review", "failed"},
            "needs_review": {"confirmed", "rejected", "failed"},
            "confirmed": set(),
            "rejected": set(),
            "failed": set(),
        }
        if target not in allowed[self.status]:
            raise ValueError("invalid_candidate_transition")
        if target in {"confirmed", "rejected"} and not reviewer_id:
            raise ValueError("reviewer_required")
        self.status = target
        self.updated_at = utc_now()
        if reviewer_id:
            self.reviewer_id = reviewer_id
            self.reviewed_at = self.updated_at


class CandidateRevisionRequest(BaseModel):
    revision: dict[str, Any] = Field(min_length=1, max_length=200)


class SourceFileScanRequest(BaseModel):
    source_file_id: str = Field(min_length=1)


class ScanImportCreateRequest(BaseModel):
    quote_id: str
    source_file_id: str
    document_type: str = "supplier_quotation"
    purpose: Literal["quotation_extraction"] = "quotation_extraction"
    schema_name: Literal["steven.s2.quotation"] = "steven.s2.quotation"
    schema_version: Literal["1.0"] = "1.0"


    @property
    def target_object_type(self) -> str:
        return "steven_quote_job"

    @property
    def target_object_id(self) -> str:
        return self.quote_id


class TenderScanImportCreateRequest(BaseModel):
    tender_id: str
    source_file_id: str
    document_type: str = "tender_source"
    purpose: Literal["tender_source_extraction"] = "tender_source_extraction"
    schema_name: Literal["steven.s1.tender_source"] = "steven.s1.tender_source"
    schema_version: Literal["1.0"] = "1.0"

    @property
    def target_object_type(self) -> str:
        return "steven_tender_job"

    @property
    def target_object_id(self) -> str:
        return self.tender_id


class ScanCandidateConfirmRequest(BaseModel):
    quote_id: str

    @model_validator(mode="after")
    def require_quote(self):
        if not self.quote_id.strip():
            raise ValueError("quote_id is required")
        return self


class DocumentFile(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    module: DocumentModule = "steven"
    document_type: str
    purpose: DocumentPurpose
    original_filename: str
    storage_key: str
    mime_type: str
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: Literal["stored", "failed"] = "stored"
    is_demo: bool = True
    created_by: str
    request_id: str
    created_at: datetime = Field(default_factory=utc_now)


class ProcessingJob(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    file_id: str
    module: DocumentModule = "steven"
    document_type: str
    purpose: DocumentPurpose
    provider: str
    model: str
    status: JobStatus = "pending"
    request_id: str
    output_json: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    def transition(self, target: JobStatus, *, output: dict[str, Any] | None = None, error_code: str | None = None) -> None:
        allowed = {
            "pending": {"running", "failed"},
            "running": {"needs_review", "failed"},
            "needs_review": {"confirmed", "rejected", "failed"},
            "confirmed": set(),
            "rejected": set(),
            "failed": set(),
        }
        if target not in allowed[self.status]:
            raise ValueError("invalid_job_transition")
        self.status = target
        self.updated_at = utc_now()
        if output is not None:
            self.output_json = output
        self.error_code = error_code
