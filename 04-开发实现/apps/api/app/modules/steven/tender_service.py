from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from html import escape
import re
import unicodedata
from uuid import uuid4

from app.core.api_response import ApiError
from app.modules.steven.tender_schemas import (
    TenderCreateRequest,
    TenderJobView,
    TenderPreviewView,
    TenderSupplierView,
    TenderTemplatePreviewRequest,
    TenderTemplateCreateRequest,
    TenderTemplateUpdateRequest,
    TenderTemplateView,
    TenderUpdateRequest,
    TenderVersionView,
)

PLACEHOLDER_PATTERN = re.compile(r"{{\s*[^{}]*\s*}}")
MANUAL_INPUT_PATTERN = re.compile(r"\[\s*待人工(?:輸入|输入|補充|补充)\s*]")
TEMPLATE_VARIABLE_PATTERN = re.compile(r"{{\s*([^{}]+?)\s*}}")


def find_unresolved_placeholders(rendered_body: str) -> list[str]:
    markers = [match.group(0) for match in PLACEHOLDER_PATTERN.finditer(rendered_body)]
    markers.extend(match.group(0) for match in MANUAL_INPUT_PATTERN.finditer(rendered_body))
    return sorted(set(markers))


def normalize_supplier_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    normalized = " ".join(normalized.split())
    return normalized.casefold()


class StevenTenderService:
    def __init__(self, repository, audit) -> None:
        self.repository = repository
        self.audit = audit

    def ensure_demo_template(self, actor: str):
        return self.repository.ensure_demo_template(actor)

    def list_templates(self) -> list[TenderTemplateView]:
        return [self._template_view(item) for item in self.repository.list_templates()]

    def create_template(self, payload: TenderTemplateCreateRequest, actor: str) -> TenderTemplateView:
        variables = self._validated_template_variables(payload.template_body, payload.variables)
        record = self.repository.create_template(
            id=str(uuid4()),
            code=f"CUSTOM-{uuid4().hex[:12].upper()}",
            version=1,
            name=payload.name,
            document_type=payload.document_type,
            template_body=payload.template_body,
            variables=variables,
            keywords=self._normalized_template_list(payload.keywords),
            is_demo=False,
            created_by=actor,
        )
        self.audit.append(
            actor=actor,
            action="tender.template.create",
            object_type="steven_template",
            object_id=record.id,
            before_after={"before": None, "after": {"name": record.name, "document_type": record.document_type, "version": record.version}},
        )
        return self._template_view(record)

    def update_template(self, template_id: str, payload: TenderTemplateUpdateRequest, actor: str) -> TenderTemplateView:
        existing = self.repository.get_template(template_id)
        if existing is None:
            raise ApiError(404, "template_not_found", "未找到可用文书模板。")
        if existing.is_demo:
            raise ApiError(403, "demo_template_immutable", "内置脱敏 DEMO 模板不可编辑。")
        variables = self._validated_template_variables(payload.template_body, payload.variables)
        record = self.repository.update_template(
            template_id,
            name=payload.name,
            document_type=payload.document_type,
            template_body=payload.template_body,
            variables=variables,
            keywords=self._normalized_template_list(payload.keywords),
        )
        self.audit.append(
            actor=actor,
            action="tender.template.update",
            object_type="steven_template",
            object_id=template_id,
            before_after={
                "before": {"name": existing.name, "document_type": existing.document_type, "version": existing.version},
                "after": {"name": record.name, "document_type": record.document_type, "version": record.version},
            },
        )
        return self._template_view(record)

    def delete_template(self, template_id: str, actor: str) -> dict[str, str | bool]:
        existing = self.repository.get_template(template_id)
        if existing is None:
            raise ApiError(404, "template_not_found", "未找到可用文书模板。")
        if existing.is_demo:
            raise ApiError(403, "demo_template_immutable", "内置脱敏 DEMO 模板不可删除。")
        if self.repository.template_in_use(template_id):
            raise ApiError(409, "template_in_use", "模板已被文书事项使用，不能删除。")
        self.repository.delete_template(template_id)
        self.audit.append(
            actor=actor,
            action="tender.template.delete",
            object_type="steven_template",
            object_id=template_id,
            before_after={"before": {"name": existing.name, "document_type": existing.document_type, "version": existing.version}, "after": None},
        )
        return {"id": template_id, "deleted": True}

    def recommend_templates(self, query: str) -> list[TenderTemplateView]:
        return [self._template_view(item) for item in self.repository.recommend_templates(query)]

    @staticmethod
    def _normalized_template_list(values: list[str]) -> list[str]:
        normalized = [unicodedata.normalize("NFKC", value).strip() for value in values]
        return list(dict.fromkeys(value for value in normalized if value))

    @classmethod
    def _validated_template_variables(cls, body: str, declared: list[str]) -> list[str]:
        extracted = cls._normalized_template_list([match.group(1) for match in TEMPLATE_VARIABLE_PATTERN.finditer(body)])
        normalized_declared = cls._normalized_template_list([
            value.removeprefix("{{").removesuffix("}}") for value in declared
        ])
        if set(extracted) != set(normalized_declared):
            raise ApiError(
                422,
                "template_variables_mismatch",
                "模板正文中的 {{变量}} 必须与变量清单完全一致。",
                {"body_variables": extracted, "declared_variables": normalized_declared},
            )
        return extracted

    def preview_template(
        self,
        template_id: str,
        tender_id: str | None = None,
        draft: TenderTemplatePreviewRequest | None = None,
    ) -> dict:
        template = self.repository.get_template(template_id)
        if template is None:
            raise ApiError(404, "template_not_found", "未找到可用文书模板。")
        context: dict[str, str] = {}
        if tender_id:
            job = self._require_job(tender_id)
            context = self._template_context(job, self.repository.suppliers_for(tender_id))
        if draft is not None:
            context = self._preview_context(context, draft)
        rendered, unresolved = self._render_template_body(template.template_body, context)
        escaped = escape(rendered)
        for marker in unresolved:
            escaped = escaped.replace(escape(marker), f"<mark>{escape(marker)}</mark>")
        return {
            "template_id": template.id,
            "template_name": template.name,
            "document_type": template.document_type,
            "html": "<br>".join(escaped.splitlines()),
            "unresolved_variables": unresolved,
        }

    def list_tenders(self) -> list[TenderJobView]:
        return [self._view(job) for job in self.repository.list_jobs()]

    def get_tender(self, tender_id: str) -> TenderJobView:
        return self._view(self._require_job(tender_id))

    def delete_tender(self, tender_id: str, actor: str) -> dict[str, str | bool]:
        job = self._require_job(tender_id)
        if job.status == "approved":
            raise ApiError(409, "approved_record_delete_forbidden", "已批准的文书事项不可删除。")
        if self.repository.versions_for(tender_id):
            raise ApiError(409, "tender_has_export_versions", "存在正式 Word 版本的文书事项不可删除。")
        before = {
            "title": job.title,
            "document_number": job.document_number,
            "status": job.status,
            "is_demo": job.is_demo,
        }
        self.repository.delete_job(tender_id)
        self.audit.append(
            actor=actor,
            action="tender.delete",
            object_type="steven_tender_job",
            object_id=tender_id,
            before_after={"before": before, "after": None},
        )
        return {"id": tender_id, "deleted": True}

    def create_tender(self, payload: TenderCreateRequest, actor: str) -> TenderJobView:
        template = self.repository.get_template(payload.template_id)
        if template is None:
            raise ApiError(404, "template_not_found", "未找到可用文书模板。")
        normalized_suppliers = self._normalized_suppliers(payload.supplier_names)
        try:
            job = self.repository.create_job(
                template_id=payload.template_id,
                title=payload.title,
                document_number=payload.document_number,
                subject=payload.subject,
                generated_date=payload.generated_date,
                deadline_date=payload.deadline_date,
                budget_min=payload.budget_min,
                budget_max=payload.budget_max,
                currency=payload.currency,
                location=payload.location,
                controlled_clauses=payload.controlled_clauses,
                is_demo=payload.is_demo,
                created_by=actor,
                updated_by=actor,
            )
            self.repository.replace_suppliers(job.id, normalized_suppliers, actor)
        except ValueError as error:
            self._raise_value_error(error)
        self.audit.append(
            actor=actor,
            action="tender.create",
            object_type="steven_tender_job",
            object_id=job.id,
            before_after={"before": None, "after": {"status": job.status, "document_number": job.document_number, "is_demo": job.is_demo}},
        )
        return self._view(job)

    def update_tender(self, tender_id: str, payload: TenderUpdateRequest, actor: str) -> TenderJobView:
        job = self._require_job(tender_id)
        if job.status not in {"draft", "draft_error", "returned"}:
            raise ApiError(409, "tender_not_editable", "当前状态不可修订文书。", {"status": job.status})
        before = {"status": job.status, "template_id": job.template_id, "updated_at": job.updated_at.isoformat()}
        values = {
            key: value
            for key, value in payload.model_dump(exclude_unset=True).items()
            if value is not None
        }
        supplier_names = values.pop("supplier_names", None)
        manual_rendered_body = values.pop("rendered_body", None)
        next_template_id = values.get("template_id")
        if next_template_id is not None and self.repository.get_template(next_template_id) is None:
            raise ApiError(404, "template_not_found", "未找到可用文书模板。")
        template_changed = next_template_id is not None and next_template_id != job.template_id
        if template_changed and manual_rendered_body is not None:
            raise ApiError(422, "template_change_with_manual_body_forbidden", "切换模板时必须重新生成草稿，不可沿用旧模板正文。")
        for key, value in values.items():
            setattr(job, key, value)
        self._validate_dates_and_budget(job.generated_date, job.deadline_date, job.budget_min, job.budget_max)
        if supplier_names is not None:
            try:
                self.repository.replace_suppliers(job.id, self._normalized_suppliers(supplier_names), actor)
            except ValueError as error:
                self._raise_value_error(error)
        if manual_rendered_body is None:
            job.status = "draft"
            job.rendered_body = None
            job.unresolved_variables = []
        else:
            job.rendered_body = manual_rendered_body
            job.unresolved_variables = find_unresolved_placeholders(manual_rendered_body)
            job.status = "draft_error" if job.unresolved_variables else "draft"
        job.submitted_by = None
        job.submitted_at = None
        job.decided_by = None
        job.decided_at = None
        job.decision_opinion = None
        try:
            self.repository.save_job(job, actor)
        except ValueError as error:
            self._raise_value_error(error)
        self.audit.append(
            actor=actor,
            action="tender.update",
            object_type="steven_tender_job",
            object_id=job.id,
            before_after={"before": before, "after": {"status": job.status, "template_id": job.template_id, "template_changed": template_changed, "approval_reset": True, "manual_body_updated": manual_rendered_body is not None, "unresolved_count": len(job.unresolved_variables)}},
        )
        return self._view(job)

    def preview(self, tender_id: str, actor: str) -> TenderPreviewView:
        job = self._require_job(tender_id)
        if job.status in {"submitted", "approved"}:
            raise ApiError(409, "tender_not_editable", "已提交或已批准文书不可重新生成草稿。", {"status": job.status})
        rendered, unresolved = self._render(job)
        before = {"status": job.status, "unresolved_variables": list(job.unresolved_variables)}
        job.rendered_body = rendered
        job.unresolved_variables = unresolved
        job.status = "draft_error" if unresolved else "draft"
        self.repository.save_job(job, actor)
        self.audit.append(
            actor=actor,
            action="tender.preview",
            object_type="steven_tender_job",
            object_id=job.id,
            before_after={"before": before, "after": {"status": job.status, "unresolved_variables": unresolved}},
        )
        return TenderPreviewView(
            tender=self._view(job),
            valid=not unresolved,
            unresolved_variables=unresolved,
        )

    def submit(self, tender_id: str, actor: str) -> TenderJobView:
        job = self._require_job(tender_id)
        if job.status not in {"draft", "draft_error", "returned"}:
            raise ApiError(409, "tender_not_submittable", "当前状态不可提交。", {"status": job.status})
        if job.rendered_body:
            rendered = job.rendered_body
            unresolved = find_unresolved_placeholders(rendered)
        else:
            rendered, unresolved = self._render(job)
        if unresolved:
            job.rendered_body = rendered
            job.unresolved_variables = unresolved
            job.status = "draft_error"
            self.repository.save_job(job, actor)
            self.audit.append(
                actor=actor,
                action="tender.submit_rejected",
                object_type="steven_tender_job",
                object_id=job.id,
                before_after={"before": None, "after": {"status": job.status, "unresolved_variables": unresolved}},
            )
            return self._view(job)
        before = {"status": job.status}
        job.rendered_body = rendered
        job.unresolved_variables = []
        job.status = "submitted"
        from app.modules.steven.tender_repository import utc_now
        job.submitted_by = actor
        job.submitted_at = utc_now()
        job.decided_by = None
        job.decided_at = None
        job.decision_opinion = None
        self.repository.save_job(job, actor)
        self.audit.append(
            actor=actor,
            action="tender.submit",
            object_type="steven_tender_job",
            object_id=job.id,
            before_after={"before": before, "after": {"status": job.status, "submitted_by": actor}},
        )
        return self._view(job)

    def approve(self, tender_id: str, actor: str, opinion: str) -> TenderJobView:
        return self._decide(tender_id, actor, "approved", opinion)

    def return_for_revision(self, tender_id: str, actor: str, opinion: str) -> TenderJobView:
        if not opinion.strip():
            raise ApiError(422, "return_opinion_required", "退回必须填写意见。")
        return self._decide(tender_id, actor, "returned", opinion)

    def _decide(self, tender_id: str, actor: str, target: str, opinion: str) -> TenderJobView:
        job = self._require_job(tender_id)
        if job.status != "submitted":
            raise ApiError(409, "approval_closed", "该文书不在待审批状态。", {"status": job.status})
        if job.submitted_by == actor:
            raise ApiError(403, "self_approval_forbidden", "提交人不得审批自己的事项。")
        before = {"status": job.status, "submitted_by": job.submitted_by}
        from app.modules.steven.tender_repository import utc_now
        job.status = target
        job.decided_by = actor
        job.decided_at = utc_now()
        job.decision_opinion = opinion.strip()
        self.repository.save_job(job, actor)
        self.audit.append(
            actor=actor,
            action="tender.approve" if target == "approved" else "tender.return",
            object_type="steven_tender_job",
            object_id=job.id,
            before_after={"before": before, "after": {"status": target, "decided_by": actor, "opinion": job.decision_opinion}},
        )
        return self._view(job)

    def list_versions(self, tender_id: str) -> list[TenderVersionView]:
        self._require_job(tender_id)
        return [self._version_view(item) for item in self.repository.versions_for(tender_id)]

    def list_audit_events(self, tender_id: str) -> list[dict]:
        self._require_job(tender_id)
        return self.audit.list_for_object(tender_id)

    def print_summary(self, tender_id: str) -> str:
        job = self._require_job(tender_id)
        if job.status != "approved":
            raise ApiError(409, "formal_print_forbidden", "仅已批准文书可以批量打印。", {"status": job.status})
        template = self.repository.get_template(job.template_id)
        if template is None:
            raise ApiError(404, "template_not_found", "未找到可用文书模板。")
        suppliers = self.repository.suppliers_for(tender_id)
        if not suppliers:
            raise ApiError(422, "supplier_required", "至少需要一名脱敏演示供应商。")
        pages: list[str] = []
        for supplier in suppliers:
            rendered, unresolved = self._render_with_template(job, template, [supplier])
            if unresolved:
                raise ApiError(409, "unresolved_variables", "存在未替换变量，不能批量打印。", {"variables": unresolved})
            pages.append(
                '<section class="supplier-page">'
                f"<header><h1>{escape(job.title)}</h1><p>{escape(supplier.supplier_name)}</p></header>"
                f"<pre>{escape(rendered)}</pre>"
                "</section>"
            )
        return "".join(
            [
                "<!doctype html><html lang=\"zh-Hant\"><head><meta charset=\"utf-8\">",
                f"<title>{escape(job.document_number)} - 批量打印</title>",
                "<style>body{font-family:'Microsoft JhengHei','Noto Sans TC',sans-serif;margin:0;color:#172033}"
                ".print-toolbar{position:sticky;top:0;padding:12px 20px;background:#fff;border-bottom:1px solid #d8dee9}"
                ".supplier-page{box-sizing:border-box;min-height:100vh;padding:28mm 24mm;break-after:page;page-break-after:always}"
                ".supplier-page:last-child{break-after:auto;page-break-after:auto}h1{font-size:22px;margin:0 0 8px}"
                "header p{margin:0 0 24px;color:#526071}pre{font:15px/1.8 'Microsoft JhengHei','Noto Sans TC',sans-serif;white-space:pre-wrap;overflow-wrap:anywhere}"
                "@media print{.print-toolbar{display:none}.supplier-page{min-height:auto}}</style></head><body>",
                '<div class="print-toolbar">已按供应商分页；浏览器打印对话框将自动打开。</div>',
                *pages,
                '<script>window.addEventListener("load",()=>window.print())</script></body></html>',
            ]
        )

    def _render(self, job, suppliers=None) -> tuple[str, list[str]]:
        self._validate_dates_and_budget(job.generated_date, job.deadline_date, job.budget_min, job.budget_max)
        suppliers = self.repository.suppliers_for(job.id) if suppliers is None else suppliers
        if not suppliers:
            raise ApiError(422, "supplier_required", "至少需要一名脱敏演示供应商。")
        template = self.repository.get_template(job.template_id)
        if template is None:
            raise ApiError(404, "template_not_found", "未找到可用文书模板。")
        return self._render_with_template(job, template, suppliers)

    def _render_with_template(self, job, template, suppliers) -> tuple[str, list[str]]:
        return self._render_template_body(template.template_body, self._template_context(job, suppliers))

    @staticmethod
    def _template_context(job, suppliers) -> dict[str, str]:
        return {
            "title": job.title,
            "document_number": job.document_number,
            "subject": job.subject,
            "generated_date": job.generated_date.isoformat(),
            "deadline_date": job.deadline_date.isoformat(),
            "budget_range": f"{job.currency} {job.budget_min:.2f} - {job.budget_max:.2f}",
            "currency": job.currency,
            "budget_min": f"{job.budget_min:.2f}",
            "budget_max": f"{job.budget_max:.2f}",
            "location": job.location,
            "supplier_name": suppliers[0].supplier_name if len(suppliers) == 1 else "、".join(item.supplier_name for item in suppliers),
            "supplier_list": "\n".join(f"- {item.supplier_name}" for item in suppliers),
            "controlled_clauses": job.controlled_clauses,
            "submission_requirements": job.controlled_clauses,
            "service_requirements": job.controlled_clauses,
            "demo_contact_name": "Demo Contact（脱敏）",
            "demo_contact_email": "demo-contact@example.invalid",
        }

    @staticmethod
    def _preview_context(base: dict[str, str], draft: TenderTemplatePreviewRequest) -> dict[str, str]:
        context = {
            "demo_contact_name": "Demo Contact（脱敏）",
            "demo_contact_email": "demo-contact@example.invalid",
            **base,
        }
        values = draft.model_dump(exclude_none=True)
        supplier_names = values.pop("supplier_names", None)
        controlled_clauses = values.pop("controlled_clauses", None)
        for key in ("title", "document_number", "subject", "location", "currency"):
            value = values.get(key)
            if value not in {None, ""}:
                context[key] = str(value)
        for key in ("generated_date", "deadline_date"):
            value = values.get(key)
            if value is not None:
                context[key] = value.isoformat()
        for key in ("budget_min", "budget_max"):
            value = values.get(key)
            if value is not None:
                context[key] = f"{value:.2f}"
        if "budget_min" in context and "budget_max" in context:
            context["budget_range"] = f"{context.get('currency', 'HKD')} {context['budget_min']} - {context['budget_max']}"
        if supplier_names:
            cleaned = [name.strip() for name in supplier_names if name.strip()]
            if cleaned:
                context["supplier_name"] = cleaned[0] if len(cleaned) == 1 else "、".join(cleaned)
                context["supplier_list"] = "\n".join(f"- {name}" for name in cleaned)
        if controlled_clauses not in {None, ""}:
            context["controlled_clauses"] = controlled_clauses
            context["submission_requirements"] = controlled_clauses
            context["service_requirements"] = controlled_clauses
        return context

    @staticmethod
    def _render_template_body(template_body: str, context: dict[str, str]) -> tuple[str, list[str]]:
        rendered = template_body
        for key, value in context.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", str(value))
        unresolved = find_unresolved_placeholders(rendered)
        return rendered, unresolved

    @staticmethod
    def _validate_dates_and_budget(generated_date, deadline_date, budget_min: Decimal, budget_max: Decimal) -> None:
        if deadline_date < generated_date + timedelta(days=3):
            raise ApiError(422, "deadline_before_minimum", "截止日期不得早于生成日期加 3 天。")
        if budget_min < 0 or budget_max < 0:
            raise ApiError(422, "budget_negative", "预算不得为负数。")
        if budget_min > budget_max:
            raise ApiError(422, "budget_range_invalid", "预算下限不得高于预算上限。")

    @staticmethod
    def _normalized_suppliers(names: list[str]) -> list[tuple[str, str]]:
        result: list[tuple[str, str]] = []
        seen: set[str] = set()
        for name in names:
            display = " ".join(unicodedata.normalize("NFKC", name).split())
            normalized = normalize_supplier_name(display)
            if not normalized:
                raise ApiError(422, "supplier_name_required", "供应商名称不可为空。")
            if normalized in seen:
                raise ApiError(409, "duplicate_supplier_name", "同一文书事项中供应商名称不得重复。", {"supplier_name": display})
            seen.add(normalized)
            result.append((display, normalized))
        return result

    def _require_job(self, tender_id: str):
        job = self.repository.get_job(tender_id)
        if job is None:
            raise ApiError(404, "tender_not_found", "未找到文书事项。")
        return job

    def _view(self, job) -> TenderJobView:
        return TenderJobView(
            id=job.id,
            template_id=job.template_id,
            title=job.title,
            document_number=job.document_number,
            subject=job.subject,
            generated_date=job.generated_date,
            deadline_date=job.deadline_date,
            budget_min=job.budget_min,
            budget_max=job.budget_max,
            currency=job.currency,
            location=job.location,
            controlled_clauses=job.controlled_clauses,
            status=job.status,
            rendered_body=job.rendered_body,
            unresolved_variables=job.unresolved_variables,
            submitted_by=job.submitted_by,
            submitted_at=job.submitted_at,
            decided_by=job.decided_by,
            decided_at=job.decided_at,
            decision_opinion=job.decision_opinion,
            is_demo=job.is_demo,
            suppliers=[TenderSupplierView(id=item.id, supplier_name=item.supplier_name) for item in self.repository.suppliers_for(job.id)],
            versions=[self._version_view(item) for item in self.repository.versions_for(job.id)],
            created_by=job.created_by,
            updated_by=job.updated_by,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )

    @staticmethod
    def _template_view(item) -> TenderTemplateView:
        return TenderTemplateView(
            id=item.id,
            code=item.code,
            version=item.version,
            name=item.name,
            document_type=item.document_type,
            template_body=item.template_body,
            variables=item.variables,
            is_demo=item.is_demo,
            keywords=item.keywords,
        )

    @staticmethod
    def _version_view(item) -> TenderVersionView:
        return TenderVersionView(
            id=item.id,
            file_id=item.file_id,
            version_number=item.version_number,
            status=item.status,
            filename=item.filename,
            storage_key=item.storage_key,
            mime_type=item.mime_type,
            sha256=item.sha256,
            size_bytes=item.size_bytes,
            failure_reason=item.failure_reason,
            created_by=item.created_by,
            created_at=item.created_at,
            published_at=item.published_at,
            export_batch_id=item.export_batch_id,
            supplier_id=item.supplier_id,
            supplier_name_snapshot=item.supplier_name_snapshot,
        )

    @staticmethod
    def _raise_value_error(error: ValueError) -> None:
        code = str(error)
        if code == "duplicate_document_number":
            raise ApiError(409, code, "文书编号已存在。") from error
        if code == "duplicate_supplier_name":
            raise ApiError(409, code, "同一文书事项中供应商名称不得重复。") from error
        raise error
