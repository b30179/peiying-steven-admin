from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

TenderStatus = Literal["draft", "draft_error", "submitted", "approved", "returned"]


class TenderTemplateView(BaseModel):
    id: str
    code: str
    version: int
    name: str
    document_type: str
    template_body: str
    variables: list[str]
    is_demo: bool
    keywords: list[str]


class TenderTemplateCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=250)
    document_type: str = Field(min_length=1, max_length=100)
    template_body: str = Field(min_length=1, max_length=30000)
    variables: list[str] = Field(default_factory=list, max_length=100)
    keywords: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("name", "document_type", "template_body")
    @classmethod
    def strip_template_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("variables", "keywords")
    @classmethod
    def clean_template_lists(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value.strip()]
        return list(dict.fromkeys(cleaned))


class TenderTemplateUpdateRequest(TenderTemplateCreateRequest):
    pass


class TenderCreateRequest(BaseModel):
    template_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=250)
    document_number: str = Field(min_length=1, max_length=100)
    subject: str = Field(min_length=1, max_length=250)
    generated_date: date
    deadline_date: date
    budget_min: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    budget_max: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    currency: str = Field(default="HKD", min_length=3, max_length=3)
    location: str = Field(min_length=1, max_length=300)
    controlled_clauses: str = Field(min_length=1, max_length=10000)
    supplier_names: list[str] = Field(min_length=1, max_length=20)
    is_demo: bool = True

    @field_validator("title", "document_number", "subject", "location", "controlled_clauses")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("supplier_names")
    @classmethod
    def validate_supplier_names(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values]
        if any(not value for value in cleaned):
            raise ValueError("供应商名称不可为空")
        return cleaned

    @model_validator(mode="after")
    def validate_rules(self):
        if self.deadline_date < self.generated_date + timedelta(days=3):
            raise ValueError("截止日期不得早于生成日期加 3 天")
        if self.budget_min > self.budget_max:
            raise ValueError("预算下限不得高于预算上限")
        return self


class TenderUpdateRequest(BaseModel):
    template_id: str | None = Field(default=None, min_length=1)
    title: str | None = Field(default=None, min_length=1, max_length=250)
    document_number: str | None = Field(default=None, min_length=1, max_length=100)
    subject: str | None = Field(default=None, min_length=1, max_length=250)
    generated_date: date | None = None
    deadline_date: date | None = None
    budget_min: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    budget_max: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    location: str | None = Field(default=None, min_length=1, max_length=300)
    controlled_clauses: str | None = Field(default=None, min_length=1, max_length=10000)
    rendered_body: str | None = Field(default=None, min_length=1, max_length=100000)
    supplier_names: list[str] | None = Field(default=None, min_length=1, max_length=20)

    @field_validator("title", "document_number", "subject", "location", "controlled_clauses", "rendered_body")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else value

    @field_validator("supplier_names")
    @classmethod
    def validate_optional_supplier_names(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        cleaned = [value.strip() for value in values]
        if any(not value for value in cleaned):
            raise ValueError("供应商名称不可为空")
        return cleaned


class TenderTemplatePreviewRequest(BaseModel):
    title: str | None = Field(default=None, max_length=250)
    document_number: str | None = Field(default=None, max_length=100)
    subject: str | None = Field(default=None, max_length=250)
    generated_date: date | None = None
    deadline_date: date | None = None
    budget_min: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    budget_max: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    location: str | None = Field(default=None, max_length=300)
    controlled_clauses: str | None = Field(default=None, max_length=10000)
    supplier_names: list[str] | None = Field(default=None, max_length=20)

    @field_validator("currency")
    @classmethod
    def normalize_optional_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else value


class TenderScanConfirmRequest(BaseModel):
    template_id: str | None = Field(default=None, min_length=1)


class TenderDecisionRequest(BaseModel):
    opinion: str = Field(default="", max_length=2000)


class TenderBatchExportRequest(BaseModel):
    supplier_ids: list[str] = Field(min_length=2, max_length=20)

    @field_validator("supplier_ids")
    @classmethod
    def validate_supplier_ids(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values]
        if any(not value for value in cleaned):
            raise ValueError("供应商 ID 不可为空")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("供应商不可重复选择")
        return cleaned


class TenderSupplierView(BaseModel):
    id: str
    supplier_name: str


class TenderVersionView(BaseModel):
    id: str
    file_id: str | None
    version_number: int
    status: Literal["reserved", "ready", "failed"]
    filename: str
    storage_key: str
    mime_type: str
    sha256: str | None
    size_bytes: int | None
    failure_reason: str | None
    created_by: str
    created_at: datetime
    published_at: datetime | None
    export_batch_id: str | None
    supplier_id: str | None
    supplier_name_snapshot: str | None


class TenderJobView(BaseModel):
    id: str
    template_id: str
    title: str
    document_number: str
    subject: str
    generated_date: date
    deadline_date: date
    budget_min: Decimal
    budget_max: Decimal
    currency: str
    location: str
    controlled_clauses: str
    status: TenderStatus
    rendered_body: str | None
    unresolved_variables: list[str]
    submitted_by: str | None
    submitted_at: datetime | None
    decided_by: str | None
    decided_at: datetime | None
    decision_opinion: str | None
    is_demo: bool
    suppliers: list[TenderSupplierView]
    versions: list[TenderVersionView]
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime


class TenderPreviewView(BaseModel):
    tender: TenderJobView
    valid: bool
    unresolved_variables: list[str]
    warning: str = "草稿仅供人工复核；未获批准不得作为正式文书。"


class TenderExportView(BaseModel):
    tender: TenderJobView
    version: TenderVersionView


class TenderBatchExportView(BaseModel):
    batch_id: str
    tender: TenderJobView
    versions: list[TenderVersionView]


class TenderProofreadingReviewRequest(BaseModel):
    decisions: dict[str, Literal["accepted", "ignored"]] = Field(default_factory=dict)


class TenderProofreadingApplyRequest(BaseModel):
    replacement_text: str = Field(max_length=10000)


class TenderProofreadingCandidateView(BaseModel):
    id: str
    status: str
    provider: str
    model: str
    candidate_json: dict
    human_revision_json: dict | None
    warnings: list
    draft_sha256: str
    created_at: datetime
    updated_at: datetime
    reviewed_at: datetime | None
