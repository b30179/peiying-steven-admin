from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from typing import Iterator
from uuid import uuid4

from sqlalchemy import Connection, Engine, text

from app.modules.steven.inventory_repository import (
    InventoryCountLineRecord,
    InventoryCountRecord,
    InventoryImportBatchRecord,
    InventoryImportRowRecord,
    InventoryItemRecord,
    InventoryVersionRecord,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PostgresInventoryRepository:
    def __init__(self, bind: Engine | Connection) -> None:
        self._bind = bind

    @contextmanager
    def _connection(self) -> Iterator[Connection]:
        if isinstance(self._bind, Connection):
            yield self._bind
        else:
            with self._bind.connect() as connection:
                yield connection

    def create_item(self, **values) -> InventoryItemRecord:
        now = utc_now()
        record = InventoryItemRecord(
            id=str(uuid4()),
            status="active",
            created_at=now,
            updated_at=now,
            **values,
        )
        with self._connection() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO steven_inventory_items
                        (id,sku,normalized_sku,item_name,category,location,book_quantity,safety_stock,target_stock,
                         status,is_demo,created_by,updated_by,created_at,updated_at)
                    VALUES
                        (:id,:sku,:normalized_sku,:item_name,:category,:location,:book_quantity,:safety_stock,:target_stock,
                         :status,:is_demo,:created_by,:updated_by,:created_at,:updated_at)
                    """
                ),
                record.__dict__,
            )
        return record

    def list_items(self) -> list[InventoryItemRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                text("SELECT * FROM steven_inventory_items ORDER BY location,item_name,sku")
            ).mappings().all()
        return [self._item(row) for row in rows]

    def get_item(self, item_id: str) -> InventoryItemRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                text("SELECT * FROM steven_inventory_items WHERE id=:id"),
                {"id": item_id},
            ).mappings().first()
        return self._item(row) if row else None

    def get_item_by_normalized_sku(
        self,
        normalized_sku: str | None,
        *,
        for_update: bool = False,
    ) -> InventoryItemRecord | None:
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection() as connection:
            row = connection.execute(
                text("SELECT * FROM steven_inventory_items WHERE normalized_sku=:normalized_sku" + suffix),
                {"normalized_sku": normalized_sku},
            ).mappings().first()
        return self._item(row) if row else None

    def save_item(self, item: InventoryItemRecord, actor: str) -> None:
        item.updated_by = actor
        item.updated_at = utc_now()
        with self._connection() as connection:
            connection.execute(
                text(
                    """
                    UPDATE steven_inventory_items
                       SET sku=:sku,normalized_sku=:normalized_sku,item_name=:item_name,category=:category,
                           location=:location,book_quantity=:book_quantity,safety_stock=:safety_stock,
                           target_stock=:target_stock,status=:status,updated_by=:updated_by,updated_at=:updated_at
                     WHERE id=:id
                    """
                ),
                item.__dict__,
            )

    def create_count(self, **values) -> InventoryCountRecord:
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
        with self._connection() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO steven_inventory_counts
                        (id,count_number,count_date,status,next_export_version,submitted_by,submitted_at,decided_by,
                         decided_at,decision_opinion,is_demo,created_by,updated_by,created_at,updated_at)
                    VALUES
                        (:id,:count_number,:count_date,:status,:next_export_version,:submitted_by,:submitted_at,:decided_by,
                         :decided_at,:decision_opinion,:is_demo,:created_by,:updated_by,:created_at,:updated_at)
                    """
                ),
                record.__dict__,
            )
        return record

    def list_counts(self) -> list[InventoryCountRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                text("SELECT * FROM steven_inventory_counts ORDER BY updated_at DESC,id")
            ).mappings().all()
        return [self._count(row) for row in rows]

    def get_count(self, count_id: str) -> InventoryCountRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                text("SELECT * FROM steven_inventory_counts WHERE id=:id"),
                {"id": count_id},
            ).mappings().first()
        return self._count(row) if row else None

    def save_count(self, count: InventoryCountRecord, actor: str) -> None:
        count.updated_by = actor
        count.updated_at = utc_now()
        with self._connection() as connection:
            connection.execute(
                text(
                    """
                    UPDATE steven_inventory_counts
                       SET count_number=:count_number,count_date=:count_date,status=:status,
                           submitted_by=:submitted_by,submitted_at=:submitted_at,decided_by=:decided_by,
                           decided_at=:decided_at,decision_opinion=:decision_opinion,
                           updated_by=:updated_by,updated_at=:updated_at
                     WHERE id=:id
                    """
                ),
                count.__dict__,
            )

    def replace_lines(self, count_id: str, lines: list[dict], actor: str) -> list[InventoryCountLineRecord]:
        with self._connection() as connection:
            connection.execute(
                text("DELETE FROM steven_inventory_count_lines WHERE inventory_count_id=:id"),
                {"id": count_id},
            )
            records: list[InventoryCountLineRecord] = []
            for values in lines:
                record = InventoryCountLineRecord(
                    id=str(uuid4()),
                    inventory_count_id=count_id,
                    updated_by=actor,
                    **values,
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO steven_inventory_count_lines
                            (id,inventory_count_id,inventory_item_id,sku_snapshot,item_name_snapshot,location_snapshot,
                             book_quantity_snapshot,safety_stock_snapshot,target_stock_snapshot,counted_quantity,
                             difference_quantity,is_low_stock,suggested_order_quantity,confirmed_order_quantity,
                             manual_reason,remark,updated_by,created_at,updated_at)
                        VALUES
                            (:id,:inventory_count_id,:inventory_item_id,:sku_snapshot,:item_name_snapshot,:location_snapshot,
                             :book_quantity_snapshot,:safety_stock_snapshot,:target_stock_snapshot,:counted_quantity,
                             :difference_quantity,:is_low_stock,:suggested_order_quantity,:confirmed_order_quantity,
                             :manual_reason,:remark,:updated_by,:created_at,:updated_at)
                        """
                    ),
                    record.__dict__,
                )
                records.append(record)
        return records

    def lines_for(self, count_id: str) -> list[InventoryCountLineRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT *
                      FROM steven_inventory_count_lines
                     WHERE inventory_count_id=:id
                     ORDER BY location_snapshot,sku_snapshot,id
                    """
                ),
                {"id": count_id},
            ).mappings().all()
        return [self._line(row) for row in rows]

    def reserve_version(self, count_id: str, actor: str, filename_template: str, storage_template: str) -> InventoryVersionRecord:
        version_id = str(uuid4())
        with self._connection() as connection:
            version_number = connection.execute(
                text(
                    """
                    UPDATE steven_inventory_counts
                       SET next_export_version=next_export_version+1,updated_at=now(),updated_by=:actor
                     WHERE id=:id
                 RETURNING next_export_version-1
                    """
                ),
                {"id": count_id, "actor": actor},
            ).scalar_one()
            filename = filename_template.format(version=version_number)
            storage_key = storage_template.format(version=version_number)
            row = connection.execute(
                text(
                    """
                    INSERT INTO steven_inventory_versions
                        (id,inventory_count_id,file_id,version_number,status,filename,storage_key,mime_type,sha256,
                         size_bytes,failure_reason,temporary_storage_key,created_by,created_at,updated_at,published_at)
                    VALUES
                        (:id,:count_id,NULL,:version,'reserved',:filename,:storage_key,:mime,NULL,NULL,NULL,NULL,
                         :actor,now(),now(),NULL)
                    RETURNING *
                    """
                ),
                {
                    "id": version_id,
                    "count_id": count_id,
                    "version": version_number,
                    "filename": filename,
                    "storage_key": storage_key,
                    "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "actor": actor,
                },
            ).mappings().one()
        return self._version(row)

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
        file_id = str(uuid4())
        with self._connection() as connection:
            version = connection.execute(
                text("SELECT * FROM steven_inventory_versions WHERE id=:id FOR UPDATE"),
                {"id": version_id},
            ).mappings().first()
            if version is None or version["status"] != "reserved":
                raise ValueError("version_not_reserved")
            connection.execute(
                text(
                    """
                    INSERT INTO files
                        (id,module,document_type,purpose,original_filename,storage_key,mime_type,size_bytes,sha256,status,
                         is_demo,created_by,request_id,created_at)
                    VALUES
                        (:id,'steven','inventory_count','approved_inventory_export',:filename,:storage_key,:mime,
                         :size_bytes,:sha256,'stored',true,:actor,:request_id,now())
                    """
                ),
                {
                    "id": file_id,
                    "filename": version["filename"],
                    "storage_key": storage_key,
                    "mime": version["mime_type"],
                    "size_bytes": size_bytes,
                    "sha256": sha256,
                    "actor": actor,
                    "request_id": request_id or "unscoped",
                },
            )
            row = connection.execute(
                text(
                    """
                    UPDATE steven_inventory_versions
                       SET file_id=:file_id,status='ready',storage_key=:storage_key,sha256=:sha256,size_bytes=:size_bytes,
                           failure_reason=NULL,published_at=now(),updated_at=now()
                     WHERE id=:id AND status='reserved'
                 RETURNING *
                    """
                ),
                {
                    "id": version_id,
                    "file_id": file_id,
                    "storage_key": storage_key,
                    "sha256": sha256,
                    "size_bytes": size_bytes,
                },
            ).mappings().first()
        if row is None:
            raise ValueError("version_not_reserved")
        return self._version(row)

    def mark_version_failed(self, version_id: str, reason: str) -> InventoryVersionRecord:
        with self._connection() as connection:
            row = connection.execute(
                text(
                    """
                    UPDATE steven_inventory_versions
                       SET status='failed',failure_reason=:reason,updated_at=now()
                     WHERE id=:id AND status='reserved'
                 RETURNING *
                    """
                ),
                {"id": version_id, "reason": reason[:2000]},
            ).mappings().first()
        if row is None:
            raise ValueError("version_not_reserved")
        return self._version(row)

    def get_version(self, version_id: str) -> InventoryVersionRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                text("SELECT * FROM steven_inventory_versions WHERE id=:id"),
                {"id": version_id},
            ).mappings().first()
        return self._version(row) if row else None

    def versions_for(self, count_id: str) -> list[InventoryVersionRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT *
                      FROM steven_inventory_versions
                     WHERE inventory_count_id=:id
                     ORDER BY version_number
                    """
                ),
                {"id": count_id},
            ).mappings().all()
        return [self._version(row) for row in rows]

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
        batch_id = str(uuid4())
        with self._connection() as connection:
            row = connection.execute(
                text(
                    """
                    INSERT INTO steven_inventory_import_batches
                        (id,original_filename,content_sha256,status,row_count,valid_count,invalid_count,
                         issues,created_by,confirmed_by,request_id,created_at,confirmed_at)
                    VALUES
                        (:id,:filename,:sha256,'preflight_ready',:row_count,:valid_count,:invalid_count,
                         CAST(:issues AS jsonb),:actor,NULL,:request_id,now(),NULL)
                    RETURNING *
                    """
                ),
                {
                    "id": batch_id,
                    "filename": original_filename,
                    "sha256": content_sha256,
                    "row_count": len(rows),
                    "valid_count": sum(item["status"] == "valid" for item in rows),
                    "invalid_count": sum(item["status"] == "invalid" for item in rows),
                    "issues": json.dumps(issues, ensure_ascii=False),
                    "actor": actor,
                    "request_id": request_id,
                },
            ).mappings().one()
            for values in rows:
                connection.execute(
                    text(
                        """
                        INSERT INTO steven_inventory_import_rows
                            (id,batch_id,row_number,raw_values,values,normalized_sku,status,errors,
                             imported_item_id,created_at,confirmed_at)
                        VALUES
                            (:id,:batch_id,:row_number,CAST(:raw_values AS jsonb),CAST(:values AS jsonb),
                             :normalized_sku,:status,CAST(:errors AS jsonb),NULL,now(),NULL)
                        """
                    ),
                    {
                        "id": str(uuid4()),
                        "batch_id": batch_id,
                        "row_number": values["row_number"],
                        "raw_values": json.dumps(values["raw_values"], ensure_ascii=False),
                        "values": json.dumps(values["values"], ensure_ascii=False),
                        "normalized_sku": values["normalized_sku"],
                        "status": values["status"],
                        "errors": json.dumps(values["errors"], ensure_ascii=False),
                    },
                )
        return self._import_batch(row)

    def get_import_batch(self, batch_id: str) -> InventoryImportBatchRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                text("SELECT * FROM steven_inventory_import_batches WHERE id=:id"),
                {"id": batch_id},
            ).mappings().first()
        return self._import_batch(row) if row else None

    def import_rows_for(self, batch_id: str) -> list[InventoryImportRowRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT *
                      FROM steven_inventory_import_rows
                     WHERE batch_id=:batch_id
                     ORDER BY row_number,id
                    """
                ),
                {"batch_id": batch_id},
            ).mappings().all()
        return [self._import_row(row) for row in rows]

    def confirm_import_batch(
        self,
        batch: InventoryImportBatchRecord,
        imported_item_ids: dict[int, str],
        actor: str,
    ) -> None:
        with self._connection() as connection:
            for row_number, item_id in imported_item_ids.items():
                updated = connection.execute(
                    text(
                        """
                        UPDATE steven_inventory_import_rows
                           SET status='confirmed',imported_item_id=:item_id,confirmed_at=now()
                         WHERE batch_id=:batch_id
                           AND row_number=:row_number
                           AND status='valid'
                        """
                    ),
                    {
                        "batch_id": batch.id,
                        "row_number": row_number,
                        "item_id": item_id,
                    },
                ).rowcount
                if updated != 1:
                    raise ValueError("import_row_state_changed")
            updated = connection.execute(
                text(
                    """
                    UPDATE steven_inventory_import_batches
                       SET status='confirmed',confirmed_by=:actor,confirmed_at=now()
                     WHERE id=:id AND status='preflight_ready'
                    """
                ),
                {"id": batch.id, "actor": actor},
            ).rowcount
        if updated != 1:
            raise ValueError("import_already_closed")

    @staticmethod
    def _item(row) -> InventoryItemRecord:
        return InventoryItemRecord(
            id=row["id"],
            sku=row["sku"],
            normalized_sku=row["normalized_sku"],
            item_name=row["item_name"],
            category=row["category"],
            location=row["location"],
            book_quantity=row["book_quantity"],
            safety_stock=row["safety_stock"],
            target_stock=row["target_stock"],
            status=row["status"],
            is_demo=row["is_demo"],
            created_by=row["created_by"],
            updated_by=row["updated_by"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _count(row) -> InventoryCountRecord:
        return InventoryCountRecord(
            id=row["id"],
            count_number=row["count_number"],
            count_date=row["count_date"],
            status=row["status"],
            next_export_version=row["next_export_version"],
            submitted_by=row["submitted_by"],
            submitted_at=row["submitted_at"],
            decided_by=row["decided_by"],
            decided_at=row["decided_at"],
            decision_opinion=row["decision_opinion"],
            is_demo=row["is_demo"],
            created_by=row["created_by"],
            updated_by=row["updated_by"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _line(row) -> InventoryCountLineRecord:
        return InventoryCountLineRecord(
            id=row["id"],
            inventory_count_id=row["inventory_count_id"],
            inventory_item_id=row["inventory_item_id"],
            sku_snapshot=row["sku_snapshot"],
            item_name_snapshot=row["item_name_snapshot"],
            location_snapshot=row["location_snapshot"],
            book_quantity_snapshot=row["book_quantity_snapshot"],
            safety_stock_snapshot=row["safety_stock_snapshot"],
            target_stock_snapshot=row["target_stock_snapshot"],
            counted_quantity=row["counted_quantity"],
            difference_quantity=row["difference_quantity"],
            is_low_stock=row["is_low_stock"],
            suggested_order_quantity=row["suggested_order_quantity"],
            confirmed_order_quantity=row["confirmed_order_quantity"],
            manual_reason=row["manual_reason"],
            remark=row["remark"],
            updated_by=row["updated_by"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _version(row) -> InventoryVersionRecord:
        return InventoryVersionRecord(
            id=row["id"],
            inventory_count_id=row["inventory_count_id"],
            version_number=row["version_number"],
            status=row["status"],
            filename=row["filename"],
            storage_key=row["storage_key"],
            mime_type=row["mime_type"],
            sha256=row["sha256"],
            size_bytes=row["size_bytes"],
            failure_reason=row["failure_reason"],
            created_by=row["created_by"],
            created_at=row["created_at"],
            published_at=row["published_at"],
            file_id=row["file_id"],
        )

    @staticmethod
    def _import_batch(row) -> InventoryImportBatchRecord:
        return InventoryImportBatchRecord(
            id=row["id"],
            original_filename=row["original_filename"],
            content_sha256=row["content_sha256"],
            status=row["status"],
            row_count=row["row_count"],
            valid_count=row["valid_count"],
            invalid_count=row["invalid_count"],
            issues=list(row["issues"] or []),
            created_by=row["created_by"],
            confirmed_by=row["confirmed_by"],
            request_id=row["request_id"],
            created_at=row["created_at"],
            confirmed_at=row["confirmed_at"],
        )

    @staticmethod
    def _import_row(row) -> InventoryImportRowRecord:
        return InventoryImportRowRecord(
            id=row["id"],
            batch_id=row["batch_id"],
            row_number=row["row_number"],
            raw_values=dict(row["raw_values"] or {}),
            values=dict(row["values"] or {}),
            normalized_sku=row["normalized_sku"],
            status=row["status"],
            errors=list(row["errors"] or []),
            imported_item_id=row["imported_item_id"],
            created_at=row["created_at"],
            confirmed_at=row["confirmed_at"],
        )
