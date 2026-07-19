from __future__ import annotations

from dataclasses import dataclass, field
from contextlib import contextmanager
from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
from threading import RLock
from typing import Any
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class QuoteJobRecord:
    id: str
    subject: str
    currency: str
    status: str
    is_demo: bool
    demo_label: str | None
    recommended_supplier_id: str | None
    non_lowest_reason: str | None
    approval_opinion: str | None
    approval_id: str | None
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str


@dataclass
class QuoteItemRecord:
    id: str
    quote_job_id: str
    item_code: str
    item: str
    specification: str
    qty: Decimal
    unit: str


@dataclass
class QuoteSupplierRecord:
    id: str
    quote_job_id: str
    supplier_code: str
    supplier_name: str
    currency: str
    valid_until: date
    freight: Decimal
    tax: Decimal
    subtotal: Decimal = Decimal("0")
    total: Decimal = Decimal("0")


@dataclass
class QuoteOfferLineRecord:
    id: str
    quote_supplier_id: str
    quote_item_id: str
    unit_price: Decimal
    line_total: Decimal
    remark: str


@dataclass
class QuoteImportBatchRecord:
    id: str
    quote_id: str
    filename: str
    sha256: str
    valid: bool
    issues: list[dict[str, Any]]
    items: list[dict[str, Any]]
    suppliers: list[dict[str, Any]]
    offers: list[dict[str, Any]]
    payload_sha256: str
    confirmed: bool = False
    confirmed_at: datetime | None = None
    confirmed_by: str | None = None


@dataclass
class QuoteApprovalRecord:
    id: str
    quote_id: str
    submitted_by: str
    status: str
    opinion: str | None
    decided_by: str | None
    created_at: datetime
    updated_at: datetime


@dataclass
class QuoteVersionRecord:
    id: str
    quote_id: str
    version_number: int
    filename: str
    storage_key: str
    sha256: str | None
    created_at: datetime
    created_by: str
    status: str = "ready"
    mime_type: str = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    size_bytes: int | None = None
    failure_reason: str | None = None
    temporary_storage_key: str | None = None
    published_at: datetime | None = None


def _import_json_default(value: Any) -> str:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"Unsupported import payload value: {type(value).__name__}")


def import_payload_sha256(
    items: list[dict[str, Any]],
    suppliers: list[dict[str, Any]],
    offers: list[dict[str, Any]],
) -> str:
    payload = {"items": items, "suppliers": suppliers, "offers": offers}
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_import_json_default,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class StevenQuoteRepository:
    def __init__(self, seed_demo: bool = True) -> None:
        self._lock = RLock()
        self._jobs: dict[str, QuoteJobRecord] = {}
        self._items: dict[str, QuoteItemRecord] = {}
        self._suppliers: dict[str, QuoteSupplierRecord] = {}
        self._offers: dict[str, QuoteOfferLineRecord] = {}
        self._batches: dict[str, QuoteImportBatchRecord] = {}
        self._approvals: dict[str, QuoteApprovalRecord] = {}
        self._versions: dict[str, list[QuoteVersionRecord]] = {}
        self._next_export_versions: dict[str, int] = {}
        if seed_demo:
            self.seed_demo_data()

    def seed_demo_data(self) -> None:
        with self._lock:
            if "demo-quote-hkd-2026" in self._jobs:
                return
            now = utc_now()
            job = QuoteJobRecord(
                id="demo-quote-hkd-2026",
                subject="脱敏演示：2026 暑期行政用品采购",
                currency="HKD",
                status="ready_for_review",
                is_demo=True,
                demo_label="脱敏演示数据，不代表真实供应商或报价",
                recommended_supplier_id=None,
                non_lowest_reason=None,
                approval_opinion=None,
                approval_id=None,
                created_at=now,
                updated_at=now,
                created_by="demo.seed",
                updated_by="demo.seed",
            )
            self._jobs[job.id] = job
            self._versions[job.id] = []
            self._next_export_versions[job.id] = 1
            item_specs = [
                ("ITEM-001", "A4 影印纸", "80gsm，500 张/包", "20", "包"),
                ("ITEM-002", "蓝色原子笔", "0.7mm", "100", "支"),
                ("ITEM-003", "订书钉", "24/6，1000 枚/盒", "50", "盒"),
                ("ITEM-004", "A4 文件夹", "透明，40 页", "60", "个"),
                ("ITEM-005", "白板笔", "黑色，可擦", "30", "支"),
            ]
            for index, (code, name, specification, qty, unit) in enumerate(item_specs, start=1):
                item = QuoteItemRecord(
                    id=f"demo-item-{index}",
                    quote_job_id=job.id,
                    item_code=code,
                    item=name,
                    specification=specification,
                    qty=Decimal(qty),
                    unit=unit,
                )
                self._items[item.id] = item
            supplier_specs = [
                ("SUP-A", "文具供应商甲（脱敏）", date(2026, 8, 15), "120", "80", ["42", "4.2", "8.5", "6", "12"]),
                ("SUP-B", "文具供应商乙（脱敏）", date(2026, 8, 20), "180", "75", ["40", "4.5", "8", "6.2", "11.5"]),
                ("SUP-C", "文具供应商丙（脱敏）", date(2026, 8, 10), "90", "100", ["43", "4", "8.2", "5.8", "12.5"]),
            ]
            items = self.items_for(job.id)
            for supplier_index, (code, name, valid_until, freight, tax, prices) in enumerate(supplier_specs, start=1):
                supplier = QuoteSupplierRecord(
                    id=f"demo-supplier-{supplier_index}",
                    quote_job_id=job.id,
                    supplier_code=code,
                    supplier_name=name,
                    currency="HKD",
                    valid_until=valid_until,
                    freight=Decimal(freight),
                    tax=Decimal(tax),
                )
                self._suppliers[supplier.id] = supplier
                for item_index, (item, price) in enumerate(zip(items, prices, strict=True), start=1):
                    unit_price = Decimal(price)
                    line = QuoteOfferLineRecord(
                        id=f"demo-offer-{supplier_index}-{item_index}",
                        quote_supplier_id=supplier.id,
                        quote_item_id=item.id,
                        unit_price=unit_price,
                        line_total=item.qty * unit_price,
                        remark="脱敏演示报价",
                    )
                    self._offers[line.id] = line

    def reset_runtime_data(self, seed_demo: bool = True) -> None:
        with self._lock:
            self._jobs.clear()
            self._items.clear()
            self._suppliers.clear()
            self._offers.clear()
            self._batches.clear()
            self._approvals.clear()
            self._versions.clear()
            self._next_export_versions.clear()
        if seed_demo:
            self.seed_demo_data()

    def create_job(self, *, subject: str, currency: str, is_demo: bool, actor: str) -> QuoteJobRecord:
        now = utc_now()
        job = QuoteJobRecord(
            id=str(uuid4()),
            subject=subject,
            currency=currency,
            status="draft",
            is_demo=is_demo,
            demo_label="脱敏演示数据" if is_demo else None,
            recommended_supplier_id=None,
            non_lowest_reason=None,
            approval_opinion=None,
            approval_id=None,
            created_at=now,
            updated_at=now,
            created_by=actor,
            updated_by=actor,
        )
        with self._lock:
            self._jobs[job.id] = job
            self._versions[job.id] = []
            self._next_export_versions[job.id] = 1
        return job

    @contextmanager
    def transaction(self):
        with self._lock:
            snapshot = deepcopy((
                self._jobs,
                self._items,
                self._suppliers,
                self._offers,
                self._batches,
                self._approvals,
                self._versions,
                self._next_export_versions,
            ))
            try:
                yield self
            except Exception:
                (
                    self._jobs,
                    self._items,
                    self._suppliers,
                    self._offers,
                    self._batches,
                    self._approvals,
                    self._versions,
                    self._next_export_versions,
                ) = snapshot
                raise

    def list_jobs(self) -> list[QuoteJobRecord]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda job: job.updated_at, reverse=True)

    def search_suppliers(self, query: str, limit: int) -> list[dict[str, Any]]:
        needle = query.strip().casefold()
        if not needle:
            return []
        aggregated: dict[tuple[str, str], dict[str, Any]] = {}
        for job in self._jobs.values():
            if job.status not in {"approved", "exported"}:
                continue
            items = {item.id: item for item in self.items_for(job.id)}
            offers_by_supplier: dict[str, list[QuoteOfferLineRecord]] = {}
            for offer in self.offers_for(job.id):
                offers_by_supplier.setdefault(offer.quote_supplier_id, []).append(offer)
            for supplier in self.suppliers_for(job.id):
                supplier_matches = needle in supplier.supplier_name.casefold()
                offered_items = [
                    items[offer.quote_item_id]
                    for offer in offers_by_supplier.get(supplier.id, [])
                    if offer.quote_item_id in items
                ]
                matched_items = {
                    item.item
                    for item in offered_items
                    if supplier_matches
                    or needle in item.item.casefold()
                    or needle in item.specification.casefold()
                }
                if not matched_items:
                    continue
                key = (supplier.supplier_code.casefold(), supplier.supplier_name.casefold())
                entry = aggregated.setdefault(
                    key,
                    {
                        "supplier_code": supplier.supplier_code,
                        "supplier_name": supplier.supplier_name,
                        "matched_items": set(),
                        "items": {},
                        "last_quote_date": job.updated_at,
                        "quote_ids": set(),
                    },
                )
                entry["matched_items"].update(matched_items)
                for item in offered_items:
                    existing = entry["items"].get(item.item_code)
                    if existing is None or job.updated_at >= existing[0]:
                        entry["items"][item.item_code] = (
                            job.updated_at,
                            {
                                "item_code": item.item_code,
                                "item": item.item,
                                "specification": item.specification,
                                "qty": item.qty,
                                "unit": item.unit,
                            },
                        )
                entry["last_quote_date"] = max(entry["last_quote_date"], job.updated_at)
                entry["quote_ids"].add(job.id)
        results = [
            {
                "supplier_code": entry["supplier_code"],
                "supplier_name": entry["supplier_name"],
                "matched_items": sorted(entry["matched_items"]),
                "items": [entry["items"][code][1] for code in sorted(entry["items"])],
                "last_quote_date": entry["last_quote_date"],
                "quote_count": len(entry["quote_ids"]),
            }
            for entry in aggregated.values()
        ]
        results.sort(key=lambda item: item["last_quote_date"], reverse=True)
        return results[: max(0, limit)]

    def get_supplier_history(self, supplier_code: str, supplier_name: str) -> dict[str, Any] | None:
        candidates = self.search_suppliers(supplier_name, max(1, len(self._suppliers)))
        return next(
            (
                {
                    "supplier_code": candidate["supplier_code"],
                    "supplier_name": candidate["supplier_name"],
                    "items": candidate["items"],
                }
                for candidate in candidates
                if candidate["supplier_code"] == supplier_code and candidate["supplier_name"] == supplier_name
            ),
            None,
        )

    def get_job(self, quote_id: str) -> QuoteJobRecord | None:
        return self._jobs.get(quote_id)

    def delete_job(self, quote_id: str) -> None:
        supplier_ids = {
            supplier.id
            for supplier in self._suppliers.values()
            if supplier.quote_job_id == quote_id
        }
        item_ids = {
            item.id
            for item in self._items.values()
            if item.quote_job_id == quote_id
        }
        for offer_id in [
            offer.id
            for offer in self._offers.values()
            if offer.quote_supplier_id in supplier_ids or offer.quote_item_id in item_ids
        ]:
            self._offers.pop(offer_id, None)
        for supplier_id in supplier_ids:
            self._suppliers.pop(supplier_id, None)
        for item_id in item_ids:
            self._items.pop(item_id, None)
        for batch_id in [batch.id for batch in self._batches.values() if batch.quote_id == quote_id]:
            self._batches.pop(batch_id, None)
        for approval_id in [approval.id for approval in self._approvals.values() if approval.quote_id == quote_id]:
            self._approvals.pop(approval_id, None)
        self._versions.pop(quote_id, None)
        self._next_export_versions.pop(quote_id, None)
        self._jobs.pop(quote_id, None)

    def touch_job(self, job: QuoteJobRecord, actor: str) -> None:
        job.updated_at = utc_now()
        job.updated_by = actor

    def items_for(self, quote_id: str) -> list[QuoteItemRecord]:
        return sorted((item for item in self._items.values() if item.quote_job_id == quote_id), key=lambda item: item.item_code)

    def suppliers_for(self, quote_id: str) -> list[QuoteSupplierRecord]:
        return sorted((supplier for supplier in self._suppliers.values() if supplier.quote_job_id == quote_id), key=lambda supplier: supplier.supplier_code)

    def offers_for(self, quote_id: str) -> list[QuoteOfferLineRecord]:
        supplier_ids = {supplier.id for supplier in self.suppliers_for(quote_id)}
        return sorted((offer for offer in self._offers.values() if offer.quote_supplier_id in supplier_ids), key=lambda offer: (offer.quote_supplier_id, offer.quote_item_id))

    def get_item(self, item_id: str) -> QuoteItemRecord | None:
        return self._items.get(item_id)

    def get_supplier(self, supplier_id: str) -> QuoteSupplierRecord | None:
        return self._suppliers.get(supplier_id)

    def add_item(self, quote_id: str, *, item_code: str, item: str, specification: str, qty: Decimal, unit: str, actor: str) -> QuoteItemRecord:
        del actor
        if any(existing.item_code.casefold() == item_code.casefold() for existing in self.items_for(quote_id)):
            raise ValueError("duplicate_item_code")
        record = QuoteItemRecord(str(uuid4()), quote_id, item_code, item, specification, qty, unit)
        self._items[record.id] = record
        return record

    def add_supplier(
        self,
        quote_id: str,
        *,
        supplier_code: str,
        supplier_name: str,
        currency: str,
        valid_until: date,
        freight: Decimal,
        tax: Decimal,
        actor: str,
    ) -> QuoteSupplierRecord:
        del actor
        suppliers = self.suppliers_for(quote_id)
        if any(existing.supplier_code.casefold() == supplier_code.casefold() for existing in suppliers):
            raise ValueError("duplicate_supplier_code")
        if any(existing.supplier_name.casefold() == supplier_name.casefold() for existing in suppliers):
            raise ValueError("duplicate_supplier_name")
        record = QuoteSupplierRecord(str(uuid4()), quote_id, supplier_code, supplier_name, currency, valid_until, freight, tax)
        self._suppliers[record.id] = record
        return record

    def add_offer(self, *, supplier_id: str, item_id: str, unit_price: Decimal, remark: str, actor: str) -> QuoteOfferLineRecord:
        del actor
        if any(offer.quote_supplier_id == supplier_id and offer.quote_item_id == item_id for offer in self._offers.values()):
            raise ValueError("duplicate_supplier_item")
        item = self._items[item_id]
        record = QuoteOfferLineRecord(str(uuid4()), supplier_id, item_id, unit_price, item.qty * unit_price, remark)
        self._offers[record.id] = record
        return record

    def save_import_batch(
        self,
        *,
        quote_id: str,
        actor: str,
        filename: str,
        sha256: str,
        valid: bool,
        issues: list[dict[str, Any]],
        items: list[dict[str, Any]],
        suppliers: list[dict[str, Any]],
        offers: list[dict[str, Any]],
    ) -> QuoteImportBatchRecord:
        del actor
        batch = QuoteImportBatchRecord(
            str(uuid4()),
            quote_id,
            filename,
            sha256,
            valid,
            issues,
            items,
            suppliers,
            offers,
            import_payload_sha256(items, suppliers, offers),
        )
        self._batches[batch.id] = batch
        return batch

    def get_import_batch(self, batch_id: str) -> QuoteImportBatchRecord | None:
        return self._batches.get(batch_id)

    @staticmethod
    def import_batch_integrity_valid(batch: QuoteImportBatchRecord) -> bool:
        return batch.payload_sha256 == import_payload_sha256(batch.items, batch.suppliers, batch.offers)

    def create_approval(self, quote_id: str, submitted_by: str) -> QuoteApprovalRecord:
        now = utc_now()
        approval = QuoteApprovalRecord(str(uuid4()), quote_id, submitted_by, "pending", None, None, now, now)
        self._approvals[approval.id] = approval
        return approval

    def get_approval(self, approval_id: str) -> QuoteApprovalRecord | None:
        return self._approvals.get(approval_id)

    def save_approval(self, approval: QuoteApprovalRecord) -> None:
        if approval.id not in self._approvals:
            raise ValueError("approval_not_found")

    def confirm_import_batch(self, batch: QuoteImportBatchRecord, actor: str) -> None:
        if batch.confirmed:
            raise ValueError("import_already_confirmed")
        batch.confirmed = True
        batch.confirmed_at = utc_now()
        batch.confirmed_by = actor

    def next_version_number(self, quote_id: str) -> int:
        return self._next_export_versions.setdefault(quote_id, 1)

    def reserve_version(self, quote_id: str, actor: str, filename: str, storage_key: str) -> QuoteVersionRecord:
        with self._lock:
            version_number = self._next_export_versions.setdefault(quote_id, 1)
            self._next_export_versions[quote_id] = version_number + 1
            filename = filename.format(version=version_number)
            storage_key = storage_key.format(version=version_number)
            version = QuoteVersionRecord(
                id=str(uuid4()),
                quote_id=quote_id,
                version_number=version_number,
                filename=filename,
                storage_key=storage_key,
                sha256=None,
                created_at=utc_now(),
                created_by=actor,
                status="reserved",
            )
            self.add_version(version)
            return version

    def mark_version_ready(self, version_id: str, *, sha256: str, size_bytes: int, published_at: datetime) -> QuoteVersionRecord:
        version = self.get_version_by_id(version_id)
        if version is None or version.status != "reserved":
            raise ValueError("version_not_reserved")
        version.status = "ready"
        version.sha256 = sha256
        version.size_bytes = size_bytes
        version.published_at = published_at
        version.failure_reason = None
        return version

    def mark_version_failed(self, version_id: str, reason: str) -> QuoteVersionRecord:
        version = self.get_version_by_id(version_id)
        if version is None:
            raise ValueError("version_not_found")
        version.status = "failed"
        version.failure_reason = reason[:2000]
        return version

    def get_version_by_id(self, version_id: str) -> QuoteVersionRecord | None:
        for versions in self._versions.values():
            for version in versions:
                if version.id == version_id:
                    return version
        return None

    def add_version(self, version: QuoteVersionRecord) -> None:
        versions = self._versions.setdefault(version.quote_id, [])
        if any(existing.version_number == version.version_number for existing in versions):
            raise ValueError("duplicate_version")
        versions.append(version)

    def versions_for(self, quote_id: str) -> list[QuoteVersionRecord]:
        return list(self._versions.get(quote_id, []))
