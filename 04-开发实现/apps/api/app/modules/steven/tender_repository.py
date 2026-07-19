from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from threading import RLock
from typing import Iterator
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class TenderTemplateRecord:
    id: str
    code: str
    version: int
    name: str
    document_type: str
    template_body: str
    variables: list[str]
    is_demo: bool = True
    keywords: list[str] = field(default_factory=list)


@dataclass
class TenderSupplierRecord:
    id: str
    tender_job_id: str
    supplier_name: str
    normalized_name: str
    created_by: str
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class TenderVersionRecord:
    id: str
    tender_job_id: str
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
    export_batch_id: str | None = None
    supplier_id: str | None = None
    supplier_name_snapshot: str | None = None


@dataclass
class TenderJobRecord:
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
    status: str
    rendered_body: str | None
    unresolved_variables: list[str]
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


DEMO_TEMPLATE = TenderTemplateRecord(
    id="template-s1-demo-001",
    code="DEMO-SERVICE-INVITATION",
    version=1,
    name="采购／服务邀请文书（脱敏演示）",
    document_type="procurement_service_invitation",
    variables=[
        "title",
        "document_number",
        "subject",
        "generated_date",
        "deadline_date",
        "budget_range",
        "location",
        "supplier_list",
        "controlled_clauses",
        "demo_contact_name",
        "demo_contact_email",
    ],
    template_body=(
        "{{title}}\n"
        "文书编号：{{document_number}}\n"
        "事项名称：{{subject}}\n"
        "生成日期：{{generated_date}}\n"
        "截止日期：{{deadline_date}}\n"
        "预算范围：{{budget_range}}\n"
        "地点：{{location}}\n\n"
        "邀请供应商：\n{{supplier_list}}\n\n"
        "受控条款：\n{{controlled_clauses}}\n\n"
        "脱敏演示联系人：{{demo_contact_name}}\n"
        "脱敏演示邮箱：{{demo_contact_email}}\n"
        "本文件仅使用脱敏演示资料。"
    ),
    keywords=["采购", "採購", "procurement", "標書", "标书", "服務", "服务", "invitation"],
)

DEMO_QUOTATION_REQUEST_TEMPLATE = TenderTemplateRecord(
    id="template-s1-demo-002",
    code="DEMO-QUOTATION-REQUEST",
    version=1,
    name="报价资料邀请文书（脱敏演示）",
    document_type="quotation_request",
    variables=[
        "title",
        "document_number",
        "supplier_name",
        "subject",
        "generated_date",
        "deadline_date",
        "currency",
        "budget_min",
        "budget_max",
        "location",
        "submission_requirements",
        "demo_contact_email",
    ],
    template_body=(
        "{{title}}\n"
        "文书编号：{{document_number}}\n"
        "致：{{supplier_name}}\n"
        "询价事项：{{subject}}\n"
        "发出日期：{{generated_date}}\n"
        "报价截止：{{deadline_date}}\n"
        "预算参考：{{currency}} {{budget_min}} 至 {{budget_max}}\n"
        "交付地点：{{location}}\n\n"
        "报价提交要求：\n{{submission_requirements}}\n\n"
        "脱敏演示邮箱：{{demo_contact_email}}\n"
        "本文件仅使用脱敏演示资料。"
    ),
    keywords=["报价", "報價", "quotation", "詢價", "询价", "比價", "比价", "request"],
)

DEMO_SERVICE_PROPOSAL_TEMPLATE = TenderTemplateRecord(
    id="template-s1-demo-003",
    code="DEMO-SERVICE-PROPOSAL-REQUEST",
    version=1,
    name="服务方案征集文书（脱敏演示）",
    document_type="service_proposal_request",
    variables=[
        "title",
        "document_number",
        "supplier_name",
        "subject",
        "deadline_date",
        "location",
        "budget_range",
        "service_requirements",
        "demo_contact_name",
        "demo_contact_email",
    ],
    template_body=(
        "{{title}}\n"
        "方案征集编号：{{document_number}}\n"
        "受邀单位：{{supplier_name}}\n"
        "服务主题：{{subject}}\n"
        "服务地点：{{location}}\n"
        "方案截止：{{deadline_date}}\n"
        "预算范围：{{budget_range}}\n\n"
        "服务方案要求：\n{{service_requirements}}\n\n"
        "脱敏演示联系人：{{demo_contact_name}}\n"
        "脱敏演示邮箱：{{demo_contact_email}}\n"
        "本文件仅使用脱敏演示资料。"
    ),
    keywords=["方案", "proposal", "征集", "徵集", "服務建議", "服务建议", "計劃", "计划"],
)

DEMO_TEMPLATES = (
    DEMO_TEMPLATE,
    DEMO_QUOTATION_REQUEST_TEMPLATE,
    DEMO_SERVICE_PROPOSAL_TEMPLATE,
)


class InMemoryTenderRepository:
    def __init__(self, seed_demo: bool = True) -> None:
        self.templates = {item.id: deepcopy(item) for item in DEMO_TEMPLATES} if seed_demo else {}
        self.jobs: dict[str, TenderJobRecord] = {}
        self.suppliers: dict[str, TenderSupplierRecord] = {}
        self.versions: dict[str, TenderVersionRecord] = {}
        self.files: dict[str, dict] = {}
        self._lock = RLock()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._lock:
            checkpoint = deepcopy((self.templates, self.jobs, self.suppliers, self.versions, self.files))
            try:
                yield
            except Exception:
                self.templates, self.jobs, self.suppliers, self.versions, self.files = checkpoint
                raise

    def ensure_demo_template(self, actor: str) -> TenderTemplateRecord:
        del actor
        for template in DEMO_TEMPLATES:
            self.templates.setdefault(template.id, deepcopy(template))
        return self.templates[DEMO_TEMPLATE.id]

    def ensure_demo_templates(self, actor: str) -> list[TenderTemplateRecord]:
        self.ensure_demo_template(actor)
        return [self.templates[item.id] for item in DEMO_TEMPLATES]

    def list_templates(self) -> list[TenderTemplateRecord]:
        return sorted(self.templates.values(), key=lambda item: (item.name, item.version))

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
        return self.templates.get(template_id)

    def create_template(self, **values) -> TenderTemplateRecord:
        values.pop("created_by", None)
        record = TenderTemplateRecord(**values)
        if any(item.code == record.code for item in self.templates.values()):
            raise ValueError("duplicate_template_code")
        self.templates[record.id] = record
        return record

    def update_template(self, template_id: str, **values) -> TenderTemplateRecord:
        record = self.templates.get(template_id)
        if record is None:
            raise ValueError("template_not_found")
        for key, value in values.items():
            setattr(record, key, value)
        record.version += 1
        return record

    def template_in_use(self, template_id: str) -> bool:
        return any(job.template_id == template_id for job in self.jobs.values())

    def delete_template(self, template_id: str) -> None:
        self.templates.pop(template_id, None)

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
        if any(job.document_number == record.document_number for job in self.jobs.values()):
            raise ValueError("duplicate_document_number")
        self.jobs[record.id] = record
        return record

    def list_jobs(self) -> list[TenderJobRecord]:
        return sorted(self.jobs.values(), key=lambda item: item.updated_at, reverse=True)

    def get_job(self, tender_id: str) -> TenderJobRecord | None:
        return self.jobs.get(tender_id)

    def delete_job(self, tender_id: str) -> None:
        for supplier_id in [
            supplier.id
            for supplier in self.suppliers.values()
            if supplier.tender_job_id == tender_id
        ]:
            self.suppliers.pop(supplier_id, None)
        self.jobs.pop(tender_id, None)

    def save_job(self, job: TenderJobRecord, actor: str) -> None:
        if any(item.id != job.id and item.document_number == job.document_number for item in self.jobs.values()):
            raise ValueError("duplicate_document_number")
        job.updated_by = actor
        job.updated_at = utc_now()
        self.jobs[job.id] = job

    def replace_suppliers(self, tender_id: str, names: list[tuple[str, str]], actor: str) -> list[TenderSupplierRecord]:
        existing_ids = [item.id for item in self.suppliers.values() if item.tender_job_id == tender_id]
        for supplier_id in existing_ids:
            self.suppliers.pop(supplier_id)
        records = []
        for display_name, normalized_name in names:
            if any(item.tender_job_id == tender_id and item.normalized_name == normalized_name for item in self.suppliers.values()):
                raise ValueError("duplicate_supplier_name")
            record = TenderSupplierRecord(str(uuid4()), tender_id, display_name, normalized_name, actor)
            self.suppliers[record.id] = record
            records.append(record)
        return records

    def suppliers_for(self, tender_id: str) -> list[TenderSupplierRecord]:
        return sorted(
            [item for item in self.suppliers.values() if item.tender_job_id == tender_id],
            key=lambda item: item.created_at,
        )

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
        job = self.jobs[tender_id]
        version_number = job.next_export_version
        job.next_export_version += 1
        record = TenderVersionRecord(
            id=str(uuid4()),
            tender_job_id=tender_id,
            version_number=version_number,
            status="reserved",
            filename=filename_template.format(version=version_number),
            storage_key=storage_template.format(version=version_number),
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            sha256=None,
            size_bytes=None,
            failure_reason=None,
            created_by=actor,
            created_at=utc_now(),
            export_batch_id=export_batch_id,
            supplier_id=supplier_id,
            supplier_name_snapshot=supplier_name_snapshot,
        )
        self.versions[record.id] = record
        return record

    def mark_version_ready(self, version_id: str, *, sha256: str, size_bytes: int, storage_key: str, actor: str, request_id: str | None) -> TenderVersionRecord:
        version = self.versions[version_id]
        if version.status != "reserved":
            raise ValueError("version_not_reserved")
        file_id = str(uuid4())
        self.files[file_id] = {
            "id": file_id,
            "module": "steven",
            "document_type": "tender_document",
            "purpose": "approved_word_export",
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

    def mark_version_failed(self, version_id: str, reason: str) -> TenderVersionRecord:
        version = self.versions[version_id]
        if version.status != "reserved":
            raise ValueError("version_not_reserved")
        version.status = "failed"
        version.failure_reason = reason[:2000]
        return version

    def get_version(self, version_id: str) -> TenderVersionRecord | None:
        return self.versions.get(version_id)

    def versions_for(self, tender_id: str) -> list[TenderVersionRecord]:
        return sorted(
            [item for item in self.versions.values() if item.tender_job_id == tender_id],
            key=lambda item: item.version_number,
        )
