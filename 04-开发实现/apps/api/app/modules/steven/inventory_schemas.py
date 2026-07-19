from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator


NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
InventoryStatus = Literal["active", "inactive"]
InventoryCountStatus = Literal["draft", "submitted", "approved", "returned"]
InventoryImportStatus = Literal["preflight_ready", "confirmed", "rejected", "failed"]
InventoryImportRowStatus = Literal["valid", "invalid", "confirmed"]


class InventoryItemCreateRequest(BaseModel):
    sku: str = Field(min_length=1, max_length=120)
    item_name: str = Field(min_length=1, max_length=250)
    category: str = Field(min_length=1, max_length=150)
    location: str = Field(min_length=1, max_length=200)
    book_quantity: NonNegativeInt
    safety_stock: NonNegativeInt
    target_stock: NonNegativeInt
    is_demo: bool = True

    @field_validator("sku", "item_name", "category", "location")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class InventoryItemUpdateRequest(BaseModel):
    sku: str | None = Field(default=None, min_length=1, max_length=120)
    item_name: str | None = Field(default=None, min_length=1, max_length=250)
    category: str | None = Field(default=None, min_length=1, max_length=150)
    location: str | None = Field(default=None, min_length=1, max_length=200)
    book_quantity: NonNegativeInt | None = None
    safety_stock: NonNegativeInt | None = None
    target_stock: NonNegativeInt | None = None
    status: InventoryStatus | None = None

    @field_validator("sku", "item_name", "category", "location")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else value


class InventoryQuickEntryRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)

    @field_validator("text")
    @classmethod
    def strip_quick_entry_text(cls, value: str) -> str:
        return value.strip()


class InventoryQuickEntryConfirmRequest(BaseModel):
    items: list[InventoryItemCreateRequest] = Field(min_length=1, max_length=50)


class InventoryCountLineInput(BaseModel):
    inventory_item_id: str = Field(min_length=1)
    counted_quantity: NonNegativeInt
    confirmed_order_quantity: NonNegativeInt | None = None
    manual_reason: str | None = Field(default=None, max_length=2000)
    remark: str | None = Field(default=None, max_length=2000)

    @field_validator("manual_reason", "remark")
    @classmethod
    def strip_optional_notes(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else value


class InventoryCountCreateRequest(BaseModel):
    count_number: str = Field(min_length=1, max_length=120)
    count_date: date
    lines: list[InventoryCountLineInput] = Field(min_length=1, max_length=500)
    is_demo: bool = True

    @field_validator("count_number")
    @classmethod
    def strip_number(cls, value: str) -> str:
        return value.strip()


class InventoryCountUpdateRequest(BaseModel):
    count_date: date | None = None
    lines: list[InventoryCountLineInput] | None = Field(default=None, min_length=1, max_length=500)


class InventoryDecisionRequest(BaseModel):
    opinion: str = Field(default="", max_length=2000)


class InventoryItemView(BaseModel):
    id: str
    sku: str
    item_name: str
    category: str
    location: str
    book_quantity: int
    safety_stock: int
    target_stock: int
    status: InventoryStatus
    is_demo: bool
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime


class InventoryCountLineView(BaseModel):
    id: str
    inventory_item_id: str
    sku: str
    item_name: str
    location: str
    book_quantity_snapshot: int
    safety_stock_snapshot: int
    target_stock_snapshot: int
    counted_quantity: int
    difference_quantity: int
    is_low_stock: bool
    suggested_order_quantity: int
    confirmed_order_quantity: int
    manual_reason: str | None
    remark: str | None


class InventoryVersionView(BaseModel):
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


class InventoryCountView(BaseModel):
    id: str
    count_number: str
    count_date: date
    status: InventoryCountStatus
    submitted_by: str | None
    submitted_at: datetime | None
    decided_by: str | None
    decided_at: datetime | None
    decision_opinion: str | None
    is_demo: bool
    lines: list[InventoryCountLineView]
    versions: list[InventoryVersionView]
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime


class InventoryExportView(BaseModel):
    count: InventoryCountView
    version: InventoryVersionView


class InventoryImportIssueView(BaseModel):
    row: int
    field: str
    code: str
    message: str


class InventoryImportRowView(BaseModel):
    id: str
    row_number: int
    raw_values: dict
    values: dict
    normalized_sku: str | None
    status: InventoryImportRowStatus
    errors: list[InventoryImportIssueView]
    imported_item_id: str | None


class InventoryImportBatchView(BaseModel):
    id: str
    original_filename: str
    content_sha256: str
    status: InventoryImportStatus
    row_count: int
    valid_count: int
    invalid_count: int
    issues: list[InventoryImportIssueView]
    rows: list[InventoryImportRowView]
    created_by: str
    confirmed_by: str | None
    request_id: str
    created_at: datetime
    confirmed_at: datetime | None
