from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TrackedQuoteMixin:
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False, default="system")
    updated_by: Mapped[str] = mapped_column(String(100), nullable=False, default="system")


class StevenQuoteJob(TrackedQuoteMixin, Base):
    __tablename__ = "steven_quote_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('draft','incomplete','ready_for_review','pending_approval','approved','exported')", name="ck_steven_quote_jobs_status"),
        CheckConstraint("next_export_version > 0", name="ck_steven_quote_jobs_next_export_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    recommended_supplier_id: Mapped[str | None] = mapped_column(ForeignKey("steven_quote_suppliers.id"), nullable=True)
    non_lowest_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_opinion: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_file_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    demo_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_id: Mapped[str | None] = mapped_column(ForeignKey("steven_quote_approvals.id", ondelete="SET NULL"), nullable=True)
    next_export_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class StevenQuoteItem(TrackedQuoteMixin, Base):
    __tablename__ = "steven_quote_items"
    __table_args__ = (
        UniqueConstraint("quote_job_id", "item_code", name="uq_steven_quote_items_job_code"),
        CheckConstraint("qty > 0", name="ck_steven_quote_items_qty_positive"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    quote_job_id: Mapped[str] = mapped_column(ForeignKey("steven_quote_jobs.id", ondelete="CASCADE"), nullable=False)
    item_code: Mapped[str] = mapped_column(String(50), nullable=False)
    item: Mapped[str] = mapped_column(String(200), nullable=False)
    specification: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    qty: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)


class StevenQuoteSupplier(TrackedQuoteMixin, Base):
    __tablename__ = "steven_quote_suppliers"
    __table_args__ = (
        UniqueConstraint("quote_job_id", "supplier_code", name="uq_steven_quote_suppliers_job_code"),
        UniqueConstraint("quote_job_id", "supplier_name", name="uq_steven_quote_suppliers_job_name"),
        CheckConstraint("freight >= 0", name="ck_steven_quote_suppliers_freight_nonnegative"),
        CheckConstraint("tax >= 0", name="ck_steven_quote_suppliers_tax_nonnegative"),
        CheckConstraint("subtotal >= 0", name="ck_steven_quote_suppliers_subtotal_nonnegative"),
        CheckConstraint("total >= 0", name="ck_steven_quote_suppliers_total_nonnegative"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    quote_job_id: Mapped[str] = mapped_column(ForeignKey("steven_quote_jobs.id", ondelete="CASCADE"), nullable=False)
    supplier_code: Mapped[str] = mapped_column(String(50), nullable=False)
    supplier_name: Mapped[str] = mapped_column(String(200), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    valid_until: Mapped[date] = mapped_column(Date, nullable=False)
    freight: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("0"))
    tax: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("0"))
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("0"))
    source_file_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class StevenQuoteOfferLine(TrackedQuoteMixin, Base):
    __tablename__ = "steven_quote_offer_lines"
    __table_args__ = (
        UniqueConstraint("quote_supplier_id", "quote_item_id", name="uq_steven_quote_offer_lines_supplier_item"),
        CheckConstraint("unit_price >= 0", name="ck_steven_quote_offer_lines_unit_price_nonnegative"),
        CheckConstraint("line_total >= 0", name="ck_steven_quote_offer_lines_total_nonnegative"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    quote_supplier_id: Mapped[str] = mapped_column(ForeignKey("steven_quote_suppliers.id", ondelete="CASCADE"), nullable=False)
    quote_item_id: Mapped[str] = mapped_column(ForeignKey("steven_quote_items.id", ondelete="CASCADE"), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    remark: Mapped[str] = mapped_column(Text, nullable=False, default="")


class StevenQuoteImportBatch(Base):
    __tablename__ = "steven_quote_import_batches"
    __table_args__ = (
        CheckConstraint("status IN ('prechecked','confirmed','rejected')", name="ck_steven_quote_import_batches_status"),
        Index("ix_steven_quote_import_batches_job_status", "quote_job_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    quote_job_id: Mapped[str] = mapped_column(ForeignKey("steven_quote_jobs.id", ondelete="CASCADE"), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="prechecked")
    issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    issues: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
    updated_by: Mapped[str] = mapped_column(String(36), nullable=False)


class StevenQuoteApproval(Base):
    __tablename__ = "steven_quote_approvals"
    __table_args__ = (
        CheckConstraint("status IN ('pending','approved','rejected')", name="ck_steven_quote_approvals_status"),
        Index("uq_steven_quote_approvals_one_pending", "quote_job_id", unique=True, postgresql_where=text("status = 'pending'")),
        Index("ix_steven_quote_approvals_status_time", "status", "submitted_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    quote_job_id: Mapped[str] = mapped_column(ForeignKey("steven_quote_jobs.id", ondelete="CASCADE"), nullable=False)
    submitted_by: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    opinion: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StevenQuoteVersion(Base):
    __tablename__ = "steven_quote_versions"
    __table_args__ = (
        UniqueConstraint("quote_job_id", "version_number", name="uq_steven_quote_versions_job_version"),
        UniqueConstraint("storage_key", name="uq_steven_quote_versions_storage_key"),
        CheckConstraint("version_number > 0", name="ck_steven_quote_versions_positive"),
        CheckConstraint("status IN ('reserved','ready','failed')", name="ck_steven_quote_versions_status"),
        CheckConstraint("size_bytes IS NULL OR size_bytes >= 0", name="ck_steven_quote_versions_size"),
        Index("ix_steven_quote_versions_status_time", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    quote_job_id: Mapped[str] = mapped_column(ForeignKey("steven_quote_jobs.id", ondelete="CASCADE"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    object_type: Mapped[str] = mapped_column(String(50), nullable=False, default="steven_quote_job")
    object_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ready")
    mime_type: Mapped[str] = mapped_column(String(150), nullable=False, default="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    temporary_storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)


class StevenQuoteAuditEvent(Base):
    __tablename__ = "steven_quote_audit_events"
    __table_args__ = (
        Index("ix_steven_quote_audit_object_time", "object_id", "occurred_at"),
        Index("ix_steven_quote_audit_actor_time", "actor_user_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    actor_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    object_type: Mapped[str] = mapped_column(String(100), nullable=False)
    object_id: Mapped[str] = mapped_column(String(36), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    before_after: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
