from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator


QuoteStatus = Literal["draft", "incomplete", "ready_for_review", "pending_approval", "approved", "exported"]


class QuoteCreateRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    currency: str = Field(default="HKD", min_length=3, max_length=3)
    is_demo: bool = False

    @field_validator("subject", "currency")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("字段不可为空")
        return value.upper() if len(value) == 3 else value


class QuoteItemCreateRequest(BaseModel):
    item_code: str = Field(min_length=1, max_length=50)
    item: str = Field(min_length=1, max_length=200)
    specification: str = Field(default="", max_length=500)
    qty: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    unit: str = Field(min_length=1, max_length=30)


class QuoteSupplierCreateRequest(BaseModel):
    supplier_code: str = Field(min_length=1, max_length=50)
    supplier_name: str = Field(min_length=1, max_length=200)
    currency: str = Field(min_length=3, max_length=3)
    valid_until: date
    freight: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    tax: Decimal = Field(ge=0, max_digits=14, decimal_places=2)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()


class QuoteOfferLineCreateRequest(BaseModel):
    quote_supplier_id: str = Field(min_length=1)
    quote_item_id: str = Field(min_length=1)
    unit_price: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    remark: str = Field(default="", max_length=1000)


class QuoteItemView(BaseModel):
    id: str
    item_code: str
    item: str
    specification: str
    qty: Decimal
    unit: str


class QuoteSupplierView(BaseModel):
    id: str
    supplier_code: str
    supplier_name: str
    currency: str
    valid_until: date
    freight: Decimal
    tax: Decimal
    subtotal: Decimal
    total: Decimal
    expired: bool


class SupplierSearchItem(BaseModel):
    item_code: str
    item: str
    specification: str
    qty: Decimal
    unit: str


class SupplierSearchResult(BaseModel):
    supplier_code: str
    supplier_name: str
    matched_items: list[str]
    items: list[SupplierSearchItem]
    last_quote_date: datetime
    quote_count: int


class QuoteSupplierReuseRequest(BaseModel):
    supplier_code: str = Field(min_length=1, max_length=50)
    supplier_name: str = Field(min_length=1, max_length=200)
    valid_until: date
    item_codes: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("supplier_code", "supplier_name")
    @classmethod
    def strip_reuse_supplier_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("item_codes")
    @classmethod
    def normalize_reuse_item_codes(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("品项编码不可为空")
        if len(set(normalized)) != len(normalized):
            raise ValueError("品项编码不可重复")
        return normalized


class QuoteOfferLineView(BaseModel):
    id: str
    quote_supplier_id: str
    quote_item_id: str
    unit_price: Decimal
    line_total: Decimal
    remark: str


class QuoteRankingEntry(BaseModel):
    rank: int
    supplier_id: str
    supplier_name: str
    subtotal: Decimal
    freight: Decimal
    tax: Decimal
    total: Decimal
    expired: bool


class QuoteComparisonView(BaseModel):
    comparison_allowed: bool
    expected_offer_count: int
    actual_offer_count: int
    blocking_reasons: list[str]
    warnings: list[str]
    ranking: list[QuoteRankingEntry]
    lowest_supplier_id: str | None


class QuoteJobView(BaseModel):
    id: str
    subject: str
    currency: str
    status: QuoteStatus
    is_demo: bool
    demo_label: str | None
    recommended_supplier_id: str | None
    non_lowest_reason: str | None
    approval_opinion: str | None
    approval_id: str | None
    items: list[QuoteItemView]
    suppliers: list[QuoteSupplierView]
    offer_lines: list[QuoteOfferLineView]
    comparison: QuoteComparisonView
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str


class QuoteRecommendationRequest(BaseModel):
    recommended_supplier_id: str = Field(min_length=1)
    non_lowest_reason: str = Field(default="", max_length=2000)
    approval_opinion: str = Field(default="", max_length=2000)


class QuoteInquiryDraftRequest(BaseModel):
    supplier_name: str = Field(min_length=1, max_length=250)
    items: list[str] = Field(default_factory=list, max_length=50)
    purpose: str = Field(min_length=1, max_length=1000)

    @field_validator("supplier_name", "purpose")
    @classmethod
    def strip_inquiry_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("items")
    @classmethod
    def clean_inquiry_items(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value.strip()]


class QuoteApprovalRequest(BaseModel):
    opinion: str = Field(min_length=1, max_length=2000)


class QuoteApprovalView(BaseModel):
    approval_id: str
    status: Literal["pending", "approved", "rejected"]
    quote: QuoteJobView


class ImportIssue(BaseModel):
    severity: Literal["error", "warning"]
    sheet: str
    row: int
    field: str
    code: str
    message: str


class QuoteImportPreview(BaseModel):
    batch_id: str
    quote_id: str
    filename: str
    sha256: str
    valid: bool
    item_count: int
    supplier_count: int
    offer_count: int
    expected_offer_count: int
    issues: list[ImportIssue]


class QuoteImportConfirmRequest(BaseModel):
    batch_id: str = Field(min_length=1)


class QuoteVersionView(BaseModel):
    id: str
    version_number: int
    filename: str
    storage_key: str
    sha256: str | None
    status: Literal["reserved", "ready", "failed"] = "ready"
    mime_type: str = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    size_bytes: int | None = None
    failure_reason: str | None = None
    created_at: datetime
    created_by: str


class QuoteExportView(BaseModel):
    quote: QuoteJobView
    version: QuoteVersionView
