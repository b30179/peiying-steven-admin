from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from typing import Iterator
from uuid import uuid4

from sqlalchemy import Connection, Engine, text

from app.modules.steven.tender_repository import (
    DEMO_TEMPLATE,
    DEMO_TEMPLATES,
    TenderJobRecord,
    TenderSupplierRecord,
    TenderTemplateRecord,
    TenderVersionRecord,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PostgresTenderRepository:
    def __init__(self, bind: Engine | Connection) -> None:
        self._bind = bind

    @contextmanager
    def _connection(self) -> Iterator[Connection]:
        if isinstance(self._bind, Connection):
            yield self._bind
        else:
            with self._bind.connect() as connection:
                yield connection

    def ensure_demo_template(self, actor: str) -> TenderTemplateRecord:
        return self.ensure_demo_templates(actor)[0]

    def ensure_demo_templates(self, actor: str) -> list[TenderTemplateRecord]:
        with self._connection() as connection:
            for template in DEMO_TEMPLATES:
                connection.execute(
                    text("""
                        INSERT INTO steven_templates
                            (id,code,version,name,document_type,template_body,variables,keywords,status,is_demo,created_by,created_at,updated_at)
                        VALUES
                            (:id,:code,:version,:name,:document_type,:template_body,CAST(:variables AS jsonb),CAST(:keywords AS jsonb),'active',true,:actor,now(),now())
                        ON CONFLICT (code,version) DO UPDATE
                        SET keywords=EXCLUDED.keywords, updated_at=now()
                    """),
                    {
                        "id": template.id,
                        "code": template.code,
                        "version": template.version,
                        "name": template.name,
                        "document_type": template.document_type,
                        "template_body": template.template_body,
                        "variables": json.dumps(template.variables, ensure_ascii=False),
                        "keywords": json.dumps(template.keywords, ensure_ascii=False),
                        "actor": actor,
                    },
                )
            codes = [item.code for item in DEMO_TEMPLATES]
            placeholders = ",".join(f":code_{index}" for index in range(len(codes)))
            rows = connection.execute(
                text(f"SELECT * FROM steven_templates WHERE code IN ({placeholders}) AND version=1 ORDER BY code"),
                {f"code_{index}": code for index, code in enumerate(codes)},
            ).mappings().all()
        records = [self._template(row) for row in rows]
        by_code = {item.code: item for item in records}
        return [by_code[item.code] for item in DEMO_TEMPLATES]

    def list_templates(self) -> list[TenderTemplateRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                text("SELECT * FROM steven_templates WHERE status='active' ORDER BY name,version")
            ).mappings().all()
        return [self._template(row) for row in rows]

    def recommend_templates(self, query: str) -> list[TenderTemplateRecord]:
        needle = query.strip().casefold()
        if not needle:
            return []
        scored = []
        for template in self.list_templates():
            score = sum(
                1
                for keyword in template.keywords
                if needle in keyword.casefold() or keyword.casefold() in needle
            )
            if score:
                scored.append((score, template.name, template.code, template))
        scored.sort(key=lambda item: (-item[0], item[1], item[2]))
        return [item[3] for item in scored[:3]]

    def get_template(self, template_id: str) -> TenderTemplateRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                text("SELECT * FROM steven_templates WHERE id=:id AND status='active'"),
                {"id": template_id},
            ).mappings().first()
        return self._template(row) if row else None

    def create_template(self, **values) -> TenderTemplateRecord:
        with self._connection() as connection:
            row = connection.execute(
                text("""
                    INSERT INTO steven_templates
                        (id,code,version,name,document_type,template_body,variables,keywords,status,is_demo,created_by,created_at,updated_at)
                    VALUES
                        (:id,:code,:version,:name,:document_type,:template_body,CAST(:variables_json AS jsonb),
                         CAST(:keywords_json AS jsonb),'active',false,:created_by,now(),now())
                    RETURNING *
                """),
                {
                    **values,
                    "variables_json": json.dumps(values["variables"], ensure_ascii=False),
                    "keywords_json": json.dumps(values["keywords"], ensure_ascii=False),
                },
            ).mappings().one()
        return self._template(row)

    def update_template(self, template_id: str, **values) -> TenderTemplateRecord:
        with self._connection() as connection:
            row = connection.execute(
                text("""
                    UPDATE steven_templates
                       SET name=:name,document_type=:document_type,template_body=:template_body,
                           variables=CAST(:variables_json AS jsonb),keywords=CAST(:keywords_json AS jsonb),
                           version=version+1,updated_at=now()
                     WHERE id=:id AND status='active'
                 RETURNING *
                """),
                {
                    "id": template_id,
                    **values,
                    "variables_json": json.dumps(values["variables"], ensure_ascii=False),
                    "keywords_json": json.dumps(values["keywords"], ensure_ascii=False),
                },
            ).mappings().first()
        if row is None:
            raise ValueError("template_not_found")
        return self._template(row)

    def template_in_use(self, template_id: str) -> bool:
        with self._connection() as connection:
            return bool(connection.execute(
                text("SELECT 1 FROM steven_tender_jobs WHERE template_id=:id LIMIT 1"),
                {"id": template_id},
            ).first())

    def delete_template(self, template_id: str) -> None:
        with self._connection() as connection:
            connection.execute(
                text("UPDATE steven_templates SET status='deleted',updated_at=now() WHERE id=:id AND status='active'"),
                {"id": template_id},
            )

    def create_job(self, **values) -> TenderJobRecord:
        now = utc_now()
        record = TenderJobRecord(
            id=str(uuid4()),
            status="draft",
            rendered_body=None,
            unresolved_variables=[],
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
                text("""
                    INSERT INTO steven_tender_jobs
                        (id,template_id,title,document_number,subject,generated_date,deadline_date,budget_min,budget_max,
                         currency,location,controlled_clauses,status,rendered_body,unresolved_variables,next_export_version,
                         submitted_by,submitted_at,decided_by,decided_at,decision_opinion,is_demo,created_by,updated_by,
                         created_at,updated_at)
                    VALUES
                        (:id,:template_id,:title,:document_number,:subject,:generated_date,:deadline_date,:budget_min,:budget_max,
                         :currency,:location,:controlled_clauses,:status,NULL,'[]'::jsonb,1,NULL,NULL,NULL,NULL,NULL,:is_demo,
                         :created_by,:updated_by,:created_at,:updated_at)
                """),
                record.__dict__,
            )
        return record

    def list_jobs(self) -> list[TenderJobRecord]:
        with self._connection() as connection:
            rows = connection.execute(text("SELECT * FROM steven_tender_jobs ORDER BY updated_at DESC")).mappings().all()
        return [self._job(row) for row in rows]

    def get_job(self, tender_id: str) -> TenderJobRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                text("SELECT * FROM steven_tender_jobs WHERE id=:id"),
                {"id": tender_id},
            ).mappings().first()
        return self._job(row) if row else None

    def delete_job(self, tender_id: str) -> None:
        with self._connection() as connection:
            connection.execute(
                text("DELETE FROM steven_tender_review_candidates WHERE tender_job_id=:id"),
                {"id": tender_id},
            )
            connection.execute(
                text("DELETE FROM steven_tender_candidate_links WHERE tender_job_id=:id"),
                {"id": tender_id},
            )
            connection.execute(text("DELETE FROM steven_tender_jobs WHERE id=:id"), {"id": tender_id})

    def save_job(self, job: TenderJobRecord, actor: str) -> None:
        job.updated_by = actor
        job.updated_at = utc_now()
        with self._connection() as connection:
            connection.execute(
                text("""
                    UPDATE steven_tender_jobs
                       SET title=:title,document_number=:document_number,subject=:subject,generated_date=:generated_date,
                           deadline_date=:deadline_date,budget_min=:budget_min,budget_max=:budget_max,location=:location,
                           controlled_clauses=:controlled_clauses,status=:status,rendered_body=:rendered_body,
                           unresolved_variables=CAST(:unresolved_variables_json AS jsonb),submitted_by=:submitted_by,
                           submitted_at=:submitted_at,decided_by=:decided_by,decided_at=:decided_at,
                           decision_opinion=:decision_opinion,updated_by=:updated_by,updated_at=:updated_at
                     WHERE id=:id
                """),
                {**job.__dict__, "unresolved_variables_json": json.dumps(job.unresolved_variables, ensure_ascii=False)},
            )

    def replace_suppliers(self, tender_id: str, names: list[tuple[str, str]], actor: str) -> list[TenderSupplierRecord]:
        with self._connection() as connection:
            connection.execute(text("DELETE FROM steven_tender_suppliers WHERE tender_job_id=:id"), {"id": tender_id})
            records = []
            for display_name, normalized_name in names:
                record = TenderSupplierRecord(str(uuid4()), tender_id, display_name, normalized_name, actor)
                connection.execute(
                    text("""
                        INSERT INTO steven_tender_suppliers
                            (id,tender_job_id,supplier_name,normalized_name,created_by,created_at)
                        VALUES (:id,:tender_job_id,:supplier_name,:normalized_name,:created_by,:created_at)
                    """),
                    record.__dict__,
                )
                records.append(record)
        return records

    def suppliers_for(self, tender_id: str) -> list[TenderSupplierRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                text("SELECT * FROM steven_tender_suppliers WHERE tender_job_id=:id ORDER BY created_at,id"),
                {"id": tender_id},
            ).mappings().all()
        return [self._supplier(row) for row in rows]

    def reserve_version(
        self,
        tender_id: str,
        actor: str,
        filename_template: str,
        storage_template: str,
        *,
        export_batch_id: str | None = None,
        supplier_id: str | None = None,
        supplier_name_snapshot: str | None = None,
    ) -> TenderVersionRecord:
        version_id = str(uuid4())
        with self._connection() as connection:
            version_number = connection.execute(
                text("""
                    UPDATE steven_tender_jobs
                       SET next_export_version=next_export_version+1,updated_at=now(),updated_by=:actor
                     WHERE id=:id
                 RETURNING next_export_version-1
                """),
                {"id": tender_id, "actor": actor},
            ).scalar_one()
            filename = filename_template.format(version=version_number)
            storage_key = storage_template.format(version=version_number)
            row = connection.execute(
                text("""
                    INSERT INTO steven_tender_versions
                        (id,tender_job_id,file_id,version_number,status,filename,storage_key,mime_type,sha256,size_bytes,
                         failure_reason,temporary_storage_key,created_by,created_at,updated_at,published_at,
                         export_batch_id,supplier_id,supplier_name_snapshot)
                    VALUES
                        (:id,:tender_id,NULL,:version,'reserved',:filename,:storage_key,:mime,NULL,NULL,NULL,NULL,:actor,now(),now(),NULL,
                         :export_batch_id,:supplier_id,:supplier_name_snapshot)
                    RETURNING *
                """),
                {
                    "id": version_id,
                    "tender_id": tender_id,
                    "version": version_number,
                    "filename": filename,
                    "storage_key": storage_key,
                    "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "actor": actor,
                    "export_batch_id": export_batch_id,
                    "supplier_id": supplier_id,
                    "supplier_name_snapshot": supplier_name_snapshot,
                },
            ).mappings().one()
        return self._version(row)

    def mark_version_ready(self, version_id: str, *, sha256: str, size_bytes: int, storage_key: str, actor: str, request_id: str | None) -> TenderVersionRecord:
        file_id = str(uuid4())
        with self._connection() as connection:
            version = connection.execute(
                text("SELECT * FROM steven_tender_versions WHERE id=:id FOR UPDATE"),
                {"id": version_id},
            ).mappings().first()
            if version is None or version["status"] != "reserved":
                raise ValueError("version_not_reserved")
            connection.execute(
                text("""
                    INSERT INTO files
                        (id,module,document_type,purpose,original_filename,storage_key,mime_type,size_bytes,sha256,status,
                         is_demo,created_by,request_id,created_at)
                    VALUES
                        (:id,'steven','tender_document','approved_word_export',:filename,:storage_key,:mime,:size_bytes,
                         :sha256,'stored',true,:actor,:request_id,now())
                """),
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
                text("""
                    UPDATE steven_tender_versions
                       SET file_id=:file_id,status='ready',storage_key=:storage_key,sha256=:sha256,size_bytes=:size_bytes,
                           failure_reason=NULL,published_at=now(),updated_at=now()
                     WHERE id=:id AND status='reserved'
                 RETURNING *
                """),
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

    def mark_version_failed(self, version_id: str, reason: str) -> TenderVersionRecord:
        with self._connection() as connection:
            row = connection.execute(
                text("""
                    UPDATE steven_tender_versions
                       SET status='failed',failure_reason=:reason,updated_at=now()
                     WHERE id=:id AND status='reserved'
                 RETURNING *
                """),
                {"id": version_id, "reason": reason[:2000]},
            ).mappings().first()
        if row is None:
            raise ValueError("version_not_reserved")
        return self._version(row)

    def get_version(self, version_id: str) -> TenderVersionRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                text("SELECT * FROM steven_tender_versions WHERE id=:id"),
                {"id": version_id},
            ).mappings().first()
        return self._version(row) if row else None

    def versions_for(self, tender_id: str) -> list[TenderVersionRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                text("SELECT * FROM steven_tender_versions WHERE tender_job_id=:id ORDER BY version_number"),
                {"id": tender_id},
            ).mappings().all()
        return [self._version(row) for row in rows]

    @staticmethod
    def _template(row) -> TenderTemplateRecord:
        return TenderTemplateRecord(
            id=row["id"],
            code=row["code"],
            version=row["version"],
            name=row["name"],
            document_type=row["document_type"],
            template_body=row["template_body"],
            variables=list(row["variables"] or []),
            is_demo=row["is_demo"],
            keywords=list(row.get("keywords") or []),
        )

    @staticmethod
    def _job(row) -> TenderJobRecord:
        return TenderJobRecord(
            id=row["id"],
            template_id=row["template_id"],
            title=row["title"],
            document_number=row["document_number"],
            subject=row["subject"],
            generated_date=row["generated_date"],
            deadline_date=row["deadline_date"],
            budget_min=row["budget_min"],
            budget_max=row["budget_max"],
            currency=row["currency"],
            location=row["location"],
            controlled_clauses=row["controlled_clauses"],
            status=row["status"],
            rendered_body=row["rendered_body"],
            unresolved_variables=list(row["unresolved_variables"] or []),
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
    def _supplier(row) -> TenderSupplierRecord:
        return TenderSupplierRecord(
            row["id"], row["tender_job_id"], row["supplier_name"], row["normalized_name"],
            row["created_by"], row["created_at"],
        )

    @staticmethod
    def _version(row) -> TenderVersionRecord:
        return TenderVersionRecord(
            id=row["id"],
            tender_job_id=row["tender_job_id"],
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
            export_batch_id=row.get("export_batch_id"),
            supplier_id=row.get("supplier_id"),
            supplier_name_snapshot=row.get("supplier_name_snapshot"),
        )
