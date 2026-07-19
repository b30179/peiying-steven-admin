from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
import json
from typing import Any, Iterator
from uuid import uuid4

from sqlalchemy import Connection, Engine, text

from app.core.audit import PostgresAuditRepository
from app.core.audit_context import current_request_id

from app.modules.steven.quote_repository import (
    QuoteApprovalRecord,
    QuoteImportBatchRecord,
    QuoteItemRecord,
    QuoteJobRecord,
    QuoteOfferLineRecord,
    QuoteSupplierRecord,
    QuoteVersionRecord,
    import_payload_sha256,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _json_default(value: Any) -> str:
    if isinstance(value, (Decimal, date, datetime)):
        return value.isoformat() if hasattr(value, "isoformat") else str(value)
    raise TypeError(f"Unsupported JSON value: {type(value).__name__}")


class PostgresQuoteRepository:
    def __init__(self, bind: Engine | Connection) -> None:
        self._bind = bind

    @contextmanager
    def _connection(self) -> Iterator[Connection]:
        if isinstance(self._bind, Connection):
            yield self._bind
        else:
            with self._bind.connect() as connection:
                yield connection

    def create_job(self, *, subject: str, currency: str, is_demo: bool, actor: str) -> QuoteJobRecord:
        record = QuoteJobRecord(
            id=str(uuid4()), subject=subject, currency=currency, status="draft", is_demo=is_demo,
            demo_label="脱敏演示数据" if is_demo else None, recommended_supplier_id=None,
            non_lowest_reason=None, approval_opinion=None, approval_id=None, created_at=utc_now(),
            updated_at=utc_now(), created_by=actor, updated_by=actor,
        )
        with self._connection() as connection:
            connection.execute(text("""
                INSERT INTO steven_quote_jobs
                    (id,subject,currency,status,is_demo,demo_label,recommended_supplier_id,non_lowest_reason,
                     approval_opinion,approval_id,next_export_version,created_at,updated_at,created_by,updated_by)
                VALUES (:id,:subject,:currency,:status,:is_demo,:demo_label,NULL,NULL,NULL,NULL,1,
                        :created_at,:updated_at,:created_by,:updated_by)
            """), record.__dict__)
        return record

    def list_jobs(self) -> list[QuoteJobRecord]:
        with self._connection() as connection:
            rows = connection.execute(text("SELECT * FROM steven_quote_jobs ORDER BY updated_at DESC")).mappings().all()
        return [self._job(row) for row in rows]

    def search_suppliers(self, query: str, limit: int) -> list[dict[str, Any]]:
        escaped = query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        if not escaped:
            return []
        with self._connection() as connection:
            rows = connection.execute(
                text("""
                    SELECT
                        s.supplier_code,
                        s.supplier_name,
                        array_agg(DISTINCT i.item ORDER BY i.item) AS matched_items,
                        MAX(j.updated_at) AS last_quote_date,
                        COUNT(DISTINCT j.id) AS quote_count
                    FROM steven_quote_suppliers AS s
                    JOIN steven_quote_offer_lines AS ol ON ol.quote_supplier_id = s.id
                    JOIN steven_quote_items AS i ON i.id = ol.quote_item_id
                    JOIN steven_quote_jobs AS j ON j.id = s.quote_job_id
                    WHERE (
                        i.item ILIKE :pattern ESCAPE '\\'
                        OR i.specification ILIKE :pattern ESCAPE '\\'
                        OR s.supplier_name ILIKE :pattern ESCAPE '\\'
                    )
                    AND j.status IN ('approved', 'exported')
                    GROUP BY s.supplier_code, s.supplier_name
                    ORDER BY last_quote_date DESC
                    LIMIT :limit
                """),
                {"pattern": f"%{escaped}%", "limit": limit},
            ).mappings().all()
            return [
                {
                    "supplier_code": row["supplier_code"],
                    "supplier_name": row["supplier_name"],
                    "matched_items": list(row["matched_items"] or []),
                    "items": self._supplier_history_items(connection, row["supplier_code"], row["supplier_name"]),
                    "last_quote_date": row["last_quote_date"],
                    "quote_count": row["quote_count"],
                }
                for row in rows
            ]

    def get_supplier_history(self, supplier_code: str, supplier_name: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            items = self._supplier_history_items(connection, supplier_code, supplier_name)
        if not items:
            return None
        return {
            "supplier_code": supplier_code,
            "supplier_name": supplier_name,
            "items": items,
        }

    @staticmethod
    def _supplier_history_items(connection: Connection, supplier_code: str, supplier_name: str) -> list[dict[str, Any]]:
        rows = connection.execute(
            text("""
                SELECT DISTINCT ON (i.item_code)
                    i.item_code,
                    i.item,
                    i.specification,
                    i.qty,
                    i.unit
                FROM steven_quote_suppliers AS s
                JOIN steven_quote_offer_lines AS ol ON ol.quote_supplier_id = s.id
                JOIN steven_quote_items AS i ON i.id = ol.quote_item_id
                JOIN steven_quote_jobs AS j ON j.id = s.quote_job_id
                WHERE s.supplier_code = :supplier_code
                  AND s.supplier_name = :supplier_name
                  AND j.status IN ('approved', 'exported')
                ORDER BY i.item_code, j.updated_at DESC, i.id DESC
            """),
            {"supplier_code": supplier_code, "supplier_name": supplier_name},
        ).mappings().all()
        return [
            {
                "item_code": row["item_code"],
                "item": row["item"],
                "specification": row["specification"],
                "qty": row["qty"],
                "unit": row["unit"],
            }
            for row in rows
        ]

    def get_job(self, quote_id: str) -> QuoteJobRecord | None:
        with self._connection() as connection:
            row = connection.execute(text("SELECT * FROM steven_quote_jobs WHERE id=:id"), {"id": quote_id}).mappings().first()
        return self._job(row) if row else None

    def delete_job(self, quote_id: str) -> None:
        with self._connection() as connection:
            connection.execute(
                text("DELETE FROM steven_quote_import_candidates WHERE quote_job_id=:id"),
                {"id": quote_id},
            )
            connection.execute(text("DELETE FROM steven_quote_jobs WHERE id=:id"), {"id": quote_id})

    def touch_job(self, job: QuoteJobRecord, actor: str) -> None:
        job.updated_at = utc_now()
        job.updated_by = actor
        with self._connection() as connection:
            connection.execute(text("""
                UPDATE steven_quote_jobs SET status=:status,recommended_supplier_id=:recommended_supplier_id,
                    non_lowest_reason=:non_lowest_reason,approval_opinion=:approval_opinion,approval_id=:approval_id,
                    updated_at=:updated_at,updated_by=:updated_by WHERE id=:id
            """), job.__dict__)

    def items_for(self, quote_id: str) -> list[QuoteItemRecord]:
        with self._connection() as connection:
            rows = connection.execute(text("SELECT * FROM steven_quote_items WHERE quote_job_id=:id ORDER BY item_code"), {"id": quote_id}).mappings().all()
        return [self._item(row) for row in rows]

    def suppliers_for(self, quote_id: str) -> list[QuoteSupplierRecord]:
        with self._connection() as connection:
            rows = connection.execute(text("""
                SELECT supplier.*,
                    COALESCE(SUM(line.line_total), 0) AS calculated_subtotal,
                    COALESCE(SUM(line.line_total), 0) + supplier.freight + supplier.tax AS calculated_total
                FROM steven_quote_suppliers supplier
                LEFT JOIN steven_quote_offer_lines line ON line.quote_supplier_id=supplier.id
                WHERE supplier.quote_job_id=:id
                GROUP BY supplier.id
                ORDER BY supplier.supplier_code
            """), {"id": quote_id}).mappings().all()
        return [self._supplier(row) for row in rows]

    def offers_for(self, quote_id: str) -> list[QuoteOfferLineRecord]:
        with self._connection() as connection:
            rows = connection.execute(text("""
                SELECT line.* FROM steven_quote_offer_lines line
                JOIN steven_quote_suppliers supplier ON supplier.id=line.quote_supplier_id
                WHERE supplier.quote_job_id=:id ORDER BY line.quote_supplier_id,line.quote_item_id
            """), {"id": quote_id}).mappings().all()
        return [self._offer(row) for row in rows]

    def get_item(self, item_id: str) -> QuoteItemRecord | None:
        with self._connection() as connection:
            row = connection.execute(text("SELECT * FROM steven_quote_items WHERE id=:id"), {"id": item_id}).mappings().first()
        return self._item(row) if row else None

    def get_supplier(self, supplier_id: str | None) -> QuoteSupplierRecord | None:
        if not supplier_id:
            return None
        with self._connection() as connection:
            row = connection.execute(text("SELECT * FROM steven_quote_suppliers WHERE id=:id"), {"id": supplier_id}).mappings().first()
        return self._supplier(row) if row else None

    def add_item(self, quote_id: str, *, item_code: str, item: str, specification: str, qty: Decimal, unit: str, actor: str) -> QuoteItemRecord:
        record = QuoteItemRecord(str(uuid4()), quote_id, item_code, item, specification, qty, unit)
        with self._connection() as connection:
            connection.execute(text("""
                INSERT INTO steven_quote_items
                    (id,quote_job_id,item_code,item,specification,qty,unit,status,created_at,updated_at,created_by,updated_by)
                VALUES (:id,:quote_job_id,:item_code,:item,:specification,:qty,:unit,'active',now(),now(),:actor,:actor)
            """), {**record.__dict__, "actor": actor})
        return record

    def add_supplier(self, quote_id: str, *, supplier_code: str, supplier_name: str, currency: str, valid_until: date, freight: Decimal, tax: Decimal, actor: str) -> QuoteSupplierRecord:
        record = QuoteSupplierRecord(str(uuid4()), quote_id, supplier_code, supplier_name, currency, valid_until, freight, tax)
        with self._connection() as connection:
            connection.execute(text("""
                INSERT INTO steven_quote_suppliers
                    (id,quote_job_id,supplier_code,supplier_name,currency,valid_until,freight,tax,subtotal,total,
                     status,created_at,updated_at,created_by,updated_by)
                VALUES (:id,:quote_job_id,:supplier_code,:supplier_name,:currency,:valid_until,:freight,:tax,0,0,
                        'active',now(),now(),:actor,:actor)
            """), {**record.__dict__, "actor": actor})
        return record

    def add_offer(self, *, supplier_id: str, item_id: str, unit_price: Decimal, remark: str, actor: str) -> QuoteOfferLineRecord:
        item = self.get_item(item_id)
        if item is None:
            raise KeyError(item_id)
        record = QuoteOfferLineRecord(str(uuid4()), supplier_id, item_id, unit_price, item.qty * unit_price, remark)
        with self._connection() as connection:
            connection.execute(text("""
                INSERT INTO steven_quote_offer_lines
                    (id,quote_supplier_id,quote_item_id,unit_price,line_total,remark,status,created_at,updated_at,created_by,updated_by)
                VALUES (:id,:quote_supplier_id,:quote_item_id,:unit_price,:line_total,:remark,'active',now(),now(),:actor,:actor)
            """), {**record.__dict__, "actor": actor})
        return record

    def save_import_batch(self, *, quote_id: str, actor: str, filename: str, sha256: str, valid: bool, issues: list[dict[str, Any]], items: list[dict[str, Any]], suppliers: list[dict[str, Any]], offers: list[dict[str, Any]]) -> QuoteImportBatchRecord:
        payload_digest = import_payload_sha256(items, suppliers, offers)
        record = QuoteImportBatchRecord(str(uuid4()), quote_id, filename, sha256, valid, issues, items, suppliers, offers, payload_digest)
        payload = json.dumps({"items": items, "suppliers": suppliers, "offers": offers}, ensure_ascii=False, default=_json_default)
        with self._connection() as connection:
            connection.execute(text("""
                INSERT INTO steven_quote_import_batches
                    (id,quote_job_id,filename,sha256,payload_sha256,status,issue_count,valid,issues,payload,created_at,created_by,updated_at,updated_by)
                VALUES (:id,:quote_id,:filename,:sha256,:payload_sha256,'prechecked',:issue_count,:valid,
                        CAST(:issues AS jsonb),CAST(:payload AS jsonb),now(),:actor,now(),:actor)
            """), {
                "id": record.id, "quote_id": quote_id, "filename": filename, "sha256": sha256,
                "issue_count": len(issues), "valid": valid, "issues": json.dumps(issues, ensure_ascii=False),
                "payload": payload, "payload_sha256": payload_digest, "actor": actor,
            })
        return record

    def get_import_batch(self, batch_id: str) -> QuoteImportBatchRecord | None:
        with self._connection() as connection:
            row = connection.execute(text("SELECT * FROM steven_quote_import_batches WHERE id=:id"), {"id": batch_id}).mappings().first()
        if not row:
            return None
        payload = row["payload"] or {}
        items = [{**item, "qty": Decimal(str(item["qty"]))} for item in payload.get("items", [])]
        suppliers = [{**supplier, "valid_until": date.fromisoformat(supplier["valid_until"]), "freight": Decimal(str(supplier["freight"])), "tax": Decimal(str(supplier["tax"]))} for supplier in payload.get("suppliers", [])]
        offers = [{**offer, "unit_price": Decimal(str(offer["unit_price"]))} for offer in payload.get("offers", [])]
        return QuoteImportBatchRecord(
            row["id"], row["quote_job_id"], row["filename"], row["sha256"], row["valid"], list(row["issues"] or []),
            items, suppliers, offers, row["payload_sha256"], row["status"] == "confirmed", row["confirmed_at"], row["confirmed_by"],
        )

    @staticmethod
    def import_batch_integrity_valid(batch: QuoteImportBatchRecord) -> bool:
        return batch.payload_sha256 == import_payload_sha256(batch.items, batch.suppliers, batch.offers)

    def confirm_import_batch(self, batch: QuoteImportBatchRecord, actor: str) -> None:
        batch.confirmed = True
        batch.confirmed_at = utc_now()
        batch.confirmed_by = actor
        with self._connection() as connection:
            result = connection.execute(text("""
                UPDATE steven_quote_import_batches SET status='confirmed',confirmed_at=:confirmed_at,
                    confirmed_by=:actor,updated_at=:confirmed_at,updated_by=:actor
                WHERE id=:id AND status='prechecked'
            """), {"id": batch.id, "confirmed_at": batch.confirmed_at, "actor": actor})
        if result.rowcount != 1:
            raise ValueError("import_already_confirmed")

    def create_approval(self, quote_id: str, submitted_by: str) -> QuoteApprovalRecord:
        now = utc_now()
        record = QuoteApprovalRecord(str(uuid4()), quote_id, submitted_by, "pending", None, None, now, now)
        with self._connection() as connection:
            connection.execute(text("""
                INSERT INTO steven_quote_approvals
                    (id,quote_job_id,submitted_by,status,created_at,updated_at,submitted_at)
                VALUES (:id,:quote_id,:submitted_by,'pending',:now,:now,:now)
            """), {"id": record.id, "quote_id": quote_id, "submitted_by": submitted_by, "now": now})
        return record

    def get_approval(self, approval_id: str) -> QuoteApprovalRecord | None:
        with self._connection() as connection:
            row = connection.execute(text("SELECT * FROM steven_quote_approvals WHERE id=:id"), {"id": approval_id}).mappings().first()
        return self._approval(row) if row else None

    def save_approval(self, approval: QuoteApprovalRecord) -> None:
        with self._connection() as connection:
            result = connection.execute(text("""
                UPDATE steven_quote_approvals SET status=:status,opinion=:opinion,decided_by=:decided_by,
                    decided_at=:updated_at,updated_at=:updated_at WHERE id=:id AND status='pending'
            """), approval.__dict__)
        if result.rowcount != 1:
            raise ValueError("approval_closed")

    def reserve_version(self, quote_id: str, actor: str, filename_template: str, storage_template: str) -> QuoteVersionRecord:
        version_id = str(uuid4())
        with self._connection() as connection:
            version_number = connection.execute(text("""
                UPDATE steven_quote_jobs SET next_export_version=next_export_version+1,updated_at=now(),updated_by=:actor
                WHERE id=:id RETURNING next_export_version-1
            """), {"id": quote_id, "actor": actor}).scalar_one()
            filename = filename_template.format(version=version_number)
            storage_key = storage_template.format(version=version_number)
            connection.execute(text("""
                INSERT INTO steven_quote_versions
                    (id,quote_job_id,version_number,filename,storage_key,sha256,created_at,created_by,
                     object_type,object_id,status,mime_type,updated_at)
                VALUES (:id,:quote_id,:version,:filename,:storage_key,NULL,now(),:actor,
                        'steven_quote_job',:quote_id,'reserved',:mime,now())
            """), {
                "id": version_id, "quote_id": quote_id, "version": version_number, "filename": filename,
                "storage_key": storage_key, "actor": actor,
                "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            })
        return QuoteVersionRecord(version_id, quote_id, version_number, filename, storage_key, None, utc_now(), actor, status="reserved")

    def mark_version_ready(self, version_id: str, *, sha256: str, size_bytes: int, published_at: datetime) -> QuoteVersionRecord:
        with self._connection() as connection:
            row = connection.execute(text("""
                UPDATE steven_quote_versions SET status='ready',sha256=:sha256,size_bytes=:size_bytes,
                    published_at=:published_at,failure_reason=NULL,updated_at=now()
                WHERE id=:id AND status='reserved' RETURNING *
            """), {"id": version_id, "sha256": sha256, "size_bytes": size_bytes, "published_at": published_at}).mappings().first()
        if row is None:
            raise ValueError("version_not_reserved")
        return self._version(row)

    def mark_version_failed(self, version_id: str, reason: str) -> QuoteVersionRecord:
        with self._connection() as connection:
            row = connection.execute(text("""
                UPDATE steven_quote_versions SET status='failed',failure_reason=:reason,updated_at=now()
                WHERE id=:id AND status='reserved' RETURNING *
            """), {"id": version_id, "reason": reason[:2000]}).mappings().first()
        if row is None:
            raise ValueError("version_not_reserved")
        return self._version(row)

    def get_version_by_id(self, version_id: str) -> QuoteVersionRecord | None:
        with self._connection() as connection:
            row = connection.execute(text("SELECT * FROM steven_quote_versions WHERE id=:id"), {"id": version_id}).mappings().first()
        return self._version(row) if row else None

    def versions_for(self, quote_id: str) -> list[QuoteVersionRecord]:
        with self._connection() as connection:
            rows = connection.execute(text("SELECT * FROM steven_quote_versions WHERE quote_job_id=:id ORDER BY version_number"), {"id": quote_id}).mappings().all()
        return [self._version(row) for row in rows]

    @staticmethod
    def _job(row) -> QuoteJobRecord:
        return QuoteJobRecord(row["id"], row["subject"], row["currency"], row["status"], row["is_demo"], row["demo_label"], row["recommended_supplier_id"], row["non_lowest_reason"], row["approval_opinion"], row["approval_id"], row["created_at"], row["updated_at"], row["created_by"], row["updated_by"])

    @staticmethod
    def _item(row) -> QuoteItemRecord:
        return QuoteItemRecord(row["id"], row["quote_job_id"], row["item_code"], row["item"], row["specification"], row["qty"], row["unit"])

    @staticmethod
    def _supplier(row) -> QuoteSupplierRecord:
        subtotal = row.get("calculated_subtotal", row["subtotal"])
        total = row.get("calculated_total", row["total"])
        return QuoteSupplierRecord(row["id"], row["quote_job_id"], row["supplier_code"], row["supplier_name"], row["currency"], row["valid_until"], row["freight"], row["tax"], subtotal, total)

    @staticmethod
    def _offer(row) -> QuoteOfferLineRecord:
        return QuoteOfferLineRecord(row["id"], row["quote_supplier_id"], row["quote_item_id"], row["unit_price"], row["line_total"], row["remark"])

    @staticmethod
    def _approval(row) -> QuoteApprovalRecord:
        return QuoteApprovalRecord(row["id"], row["quote_job_id"], row["submitted_by"], row["status"], row["opinion"], row["decided_by"], row["created_at"], row["updated_at"])

    @staticmethod
    def _version(row) -> QuoteVersionRecord:
        return QuoteVersionRecord(
            row["id"], row["quote_job_id"], row["version_number"], row["filename"], row["storage_key"], row["sha256"],
            row["created_at"], row["created_by"], row["status"], row["mime_type"], row["size_bytes"],
            row["failure_reason"], row["temporary_storage_key"], row["published_at"],
        )


class PostgresQuoteAuditRepository:
    def __init__(self, bind: Engine | Connection) -> None:
        self._bind = bind

    @contextmanager
    def _connection(self) -> Iterator[Connection]:
        if isinstance(self._bind, Connection):
            yield self._bind
        else:
            with self._bind.connect() as connection:
                yield connection

    def append(self, *, actor: str, action: str, object_type: str, object_id: str, before_after: dict[str, Any]):
        event_id = str(uuid4())
        request_id = current_request_id()
        with self._connection() as connection:
            connection.execute(text("""
                INSERT INTO steven_quote_audit_events
                    (id,actor_user_id,action,object_type,object_id,occurred_at,request_id,before_after)
                VALUES (:id,:actor,:action,:object_type,:object_id,now(),:request_id,CAST(:before_after AS jsonb))
            """), {
                "id": event_id, "actor": actor, "action": action, "object_type": object_type,
                "object_id": object_id, "request_id": request_id, "before_after": json.dumps(before_after, ensure_ascii=False, default=_json_default),
            })
            if action in {"quote.submit", "quote.approve", "quote.reject", "quote.delete"}:
                PostgresAuditRepository(connection).append(
                    actor=actor,
                    action=action,
                    object_type=object_type,
                    object_id=object_id,
                    request_id=request_id,
                    before_after=before_after,
                )
        return {"id": event_id}

    def list(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(text("SELECT * FROM steven_quote_audit_events ORDER BY occurred_at")).mappings().all()
        return [self._view(row) for row in rows]

    def list_for_object(self, object_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(text("""
                SELECT * FROM steven_quote_audit_events
                WHERE object_id=:id OR before_after @> CAST(:needle AS jsonb)
                ORDER BY occurred_at
            """), {"id": object_id, "needle": json.dumps({"quote_id": object_id})}).mappings().all()
        return [self._view(row) for row in rows]

    @staticmethod
    def _view(row) -> dict[str, Any]:
        return {
            "actor": row["actor_user_id"], "action": row["action"], "object_type": row["object_type"],
            "object_id": row["object_id"], "timestamp": row["occurred_at"].isoformat(), "request_id": row["request_id"], "before_after": row["before_after"],
        }
