from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from threading import RLock
from typing import Iterator
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class InventoryItemRecord:
    id: str
    sku: str
    normalized_sku: str
    item_name: str
    category: str
    location: str
    book_quantity: int
    safety_stock: int
    target_stock: int
    status: str
    is_demo: bool
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime


@dataclass
class InventoryCountRecord:
    id: str
    count_number: str
    count_date: date
    status: str
    next_export_version: int
    submitted_by: str | None
    submitted_at: datetime | None
    decided_by: str | None
    decided_at: datetime | None
    decision_opinion: str | None
    is_demo: bool
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime


@dataclass
class InventoryCountLineRecord:
    id: str
    inventory_count_id: str
    inventory_item_id: str
    sku_snapshot: str
    item_name_snapshot: str
    location_snapshot: str
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
    updated_by: str
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class InventoryVersionRecord:
    id: str
    inventory_count_id: str
    version_number: int
    status: str
    filename: str
    storage_key: str
    mime_type: str
    sha256: str | None
    size_bytes: int | None
    failure_reason: str | None
    created_by: str
    created_at: datetime
    published_at: datetime | None = None
    file_id: str | None = None


@dataclass
class InventoryImportRowRecord:
    id: str
    batch_id: str
    row_number: int
    raw_values: dict
    values: dict
    normalized_sku: str | None
    status: str
    errors: list[dict]
    imported_item_id: str | None
    created_at: datetime
    confirmed_at: datetime | None = None


@dataclass
class InventoryImportBatchRecord:
    id: str
    original_filename: str
    content_sha256: str
    status: str
    row_count: int
    valid_count: int
    invalid_count: int
    issues: list[dict]
    created_by: str
    confirmed_by: str | None
    request_id: str
    created_at: datetime
    confirmed_at: datetime | None = None


class InMemoryInventoryRepository:
    def __init__(self) -> None:
        self.items: dict[str, InventoryItemRecord] = {}
        self.counts: dict[str, InventoryCountRecord] = {}
        self.lines: dict[str, InventoryCountLineRecord] = {}
        self.versions: dict[str, InventoryVersionRecord] = {}
        self.files: dict[str, dict] = {}
        self.import_batches: dict[str, InventoryImportBatchRecord] = {}
        self.import_rows: dict[str, InventoryImportRowRecord] = {}
        self._lock = RLock()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._lock:
            checkpoint = deepcopy(
                (
                    self.items,
                    self.counts,
                    self.lines,
                    self.versions,
                    self.files,
                    self.import_batches,
                    self.import_rows,
                )
            )
            try:
                yield
            except Exception:
                (
                    self.items,
                    self.counts,
                    self.lines,
                    self.versions,
                    self.files,
                    self.import_batches,
                    self.import_rows,
                ) = checkpoint
                raise

    def create_item(self, **values) -> InventoryItemRecord:
        if any(item.normalized_sku == values["normalized_sku"] for item in self.items.values()):
            raise ValueError("duplicate_sku")
        now = utc_now()
        record = InventoryItemRecord(
            id=str(uuid4()),
            status="active",
            created_at=now,
            updated_at=now,
            **values,
        )
        self.items[record.id] = record
        return record

    def list_items(self) -> list[InventoryItemRecord]:
        return sorted(self.items.values(), key=lambda item: (item.location, item.item_name, item.sku))

    def get_item(self, item_id: str) -> InventoryItemRecord | None:
        return self.items.get(item_id)

    def get_item_by_normalized_sku(
        self,
        normalized_sku: str | None,
        *,
        for_update: bool = False,
    ) -> InventoryItemRecord | None:
        del for_update
        return next(
            (item for item in self.items.values() if item.normalized_sku == normalized_sku),
            None,
        )

    def save_item(self, item: InventoryItemRecord, actor: str) -> None:
        if any(
            existing.id != item.id and existing.normalized_sku == item.normalized_sku
            for existing in self.items.values()
        ):
            raise ValueError("duplicate_sku")
        item.updated_by = actor
        item.updated_at = utc_now()
        self.items[item.id] = item

    def create_count(self, **values) -> InventoryCountRecord:
        if any(item.count_number == values["count_number"] for item in self.counts.values()):
            raise ValueError("duplicate_count_number")
        now = utc_now()
        record = InventoryCountRecord(
            id=str(uuid4()),
            status="draft",
            next_export_version=1,
            submitted_by=None,
            submitted_at=None,
            decided_by=None,
            decided_at=None,
            decision_opinion=None,
            created_at=now,
            updated_at=now,
            **values,
        )
        self.counts[record.id] = record
        return record

    def list_counts(self) -> list[InventoryCountRecord]:
        return sorted(self.counts.values(), key=lambda item: item.updated_at, reverse=True)

    def get_count(self, count_id: str) -> InventoryCountRecord | None:
        return self.counts.get(count_id)

    def save_count(self, count: InventoryCountRecord, actor: str) -> None:
        if any(
            existing.id != count.id and existing.count_number == count.count_number
            for existing in self.counts.values()
        ):
            raise ValueError("duplicate_count_number")
        count.updated_by = actor
        count.updated_at = utc_now()
        self.counts[count.id] = count

    def replace_lines(self, count_id: str, lines: list[dict], actor: str) -> list[InventoryCountLineRecord]:
        for line_id in [item.id for item in self.lines.values() if item.inventory_count_id == count_id]:
            self.lines.pop(line_id)
        records: list[InventoryCountLineRecord] = []
        seen: set[str] = set()
        for values in lines:
            item_id = values["inventory_item_id"]
            if item_id in seen:
                raise ValueError("duplicate_count_item")
            seen.add(item_id)
            record = InventoryCountLineRecord(id=str(uuid4()), inventory_count_id=count_id, updated_by=actor, **values)
            self.lines[record.id] = record
            records.append(record)
        return records

    def lines_for(self, count_id: str) -> list[InventoryCountLineRecord]:
        return sorted(
            [item for item in self.lines.values() if item.inventory_count_id == count_id],
            key=lambda item: (item.location_snapshot, item.sku_snapshot),
        )

    def reserve_version(self, count_id: str, actor: str, filename_template: str, storage_template: str) -> InventoryVersionRecord:
        count = self.counts[count_id]
        version_number = count.next_export_version
        count.next_export_version += 1
        record = InventoryVersionRecord(
            id=str(uuid4()),
            inventory_count_id=count_id,
            version_number=version_number,
            status="reserved",
            filename=filename_template.format(version=version_number),
            storage_key=storage_template.format(version=version_number),
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            sha256=None,
            size_bytes=None,
            failure_reason=None,
            created_by=actor,
            created_at=utc_now(),
        )
        self.versions[record.id] = record
        return record

    def mark_version_ready(
        self,
        version_id: str,
        *,
        sha256: str,
        size_bytes: int,
        storage_key: str,
        actor: str,
        request_id: str | None,
    ) -> InventoryVersionRecord:
        version = self.versions[version_id]
        if version.status != "reserved":
            raise ValueError("version_not_reserved")
        file_id = str(uuid4())
        self.files[file_id] = {
            "id": file_id,
            "module": "steven",
            "document_type": "inventory_count",
            "purpose": "approved_inventory_export",
            "storage_key": storage_key,
            "sha256": sha256,
            "size_bytes": size_bytes,
            "created_by": actor,
            "request_id": request_id,
        }
        version.file_id = file_id
        version.storage_key = storage_key
        version.sha256 = sha256
        version.size_bytes = size_bytes
        version.status = "ready"
        version.published_at = utc_now()
        return version

    def mark_version_failed(self, version_id: str, reason: str) -> InventoryVersionRecord:
        version = self.versions[version_id]
        if version.status != "reserved":
            raise ValueError("version_not_reserved")
        version.status = "failed"
        version.failure_reason = reason[:2000]
        return version

    def get_version(self, version_id: str) -> InventoryVersionRecord | None:
        return self.versions.get(version_id)

    def versions_for(self, count_id: str) -> list[InventoryVersionRecord]:
        return sorted(
            [item for item in self.versions.values() if item.inventory_count_id == count_id],
            key=lambda item: item.version_number,
        )

    def create_import_batch(
        self,
        *,
        original_filename: str,
        content_sha256: str,
        rows: list[dict],
        issues: list[dict],
        actor: str,
        request_id: str,
    ) -> InventoryImportBatchRecord:
        now = utc_now()
        batch = InventoryImportBatchRecord(
            id=str(uuid4()),
            original_filename=original_filename,
            content_sha256=content_sha256,
            status="preflight_ready",
            row_count=len(rows),
            valid_count=sum(row["status"] == "valid" for row in rows),
            invalid_count=sum(row["status"] == "invalid" for row in rows),
            issues=deepcopy(issues),
            created_by=actor,
            confirmed_by=None,
            request_id=request_id,
            created_at=now,
        )
        self.import_batches[batch.id] = batch
        for values in rows:
            row = InventoryImportRowRecord(
                id=str(uuid4()),
                batch_id=batch.id,
                imported_item_id=None,
                created_at=now,
                **deepcopy(values),
            )
            self.import_rows[row.id] = row
        return batch

    def get_import_batch(self, batch_id: str) -> InventoryImportBatchRecord | None:
        return self.import_batches.get(batch_id)

    def import_rows_for(self, batch_id: str) -> list[InventoryImportRowRecord]:
        return sorted(
            [row for row in self.import_rows.values() if row.batch_id == batch_id],
            key=lambda row: row.row_number,
        )

    def confirm_import_batch(
        self,
        batch: InventoryImportBatchRecord,
        imported_item_ids: dict[int, str],
        actor: str,
    ) -> None:
        if batch.status != "preflight_ready":
            raise ValueError("import_already_closed")
        now = utc_now()
        for row in self.import_rows_for(batch.id):
            row.status = "confirmed"
            row.imported_item_id = imported_item_ids[row.row_number]
            row.confirmed_at = now
        batch.status = "confirmed"
        batch.confirmed_by = actor
        batch.confirmed_at = now
