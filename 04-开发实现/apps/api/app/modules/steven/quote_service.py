from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from app.core.api_response import ApiError
from app.core.audit import AuditRepository
from app.modules.steven.quote_excel import LocalAppendOnlyQuoteStorage, QuoteExcelExporter, QuoteImportParser
from app.modules.steven.quote_repository import QuoteJobRecord, QuoteVersionRecord, StevenQuoteRepository
from app.modules.steven.quote_schemas import (
    QuoteApprovalView,
    QuoteCreateRequest,
    QuoteExportView,
    QuoteImportPreview,
    QuoteItemCreateRequest,
    QuoteJobView,
    QuoteOfferLineCreateRequest,
    QuoteRecommendationRequest,
    QuoteSupplierCreateRequest,
    QuoteSupplierReuseRequest,
    QuoteVersionView,
    SupplierSearchResult,
)


class StevenQuoteService:
    def __init__(
        self,
        repository: StevenQuoteRepository,
        audit: AuditRepository,
        parser: QuoteImportParser,
        exporter: QuoteExcelExporter,
        storage: LocalAppendOnlyQuoteStorage | None = None,
    ) -> None:
        self.repository = repository
        self._audit = audit
        self._parser = parser
        self._exporter = exporter
        self._storage = storage or LocalAppendOnlyQuoteStorage(exporter.data_root)

    def list_quotes(self) -> list[QuoteJobView]:
        return [self._quote_view(job) for job in self.repository.list_jobs()]

    def search_suppliers(self, query: str, limit: int) -> list[SupplierSearchResult]:
        return [SupplierSearchResult.model_validate(item) for item in self.repository.search_suppliers(query, limit)]

    def get_quote(self, quote_id: str) -> QuoteJobView:
        return self._quote_view(self._require_job(quote_id))

    def recommend_supplier(self, quote_id: str, ai_assist) -> dict:
        quote = self.get_quote(quote_id)
        if not quote.comparison.comparison_allowed:
            raise ApiError(409, "quote_comparison_incomplete", "报价数据不完整，暂不能进行 AI 分析。")
        result = ai_assist.recommend_quote(quote.model_dump(mode="json"))
        suppliers = {supplier.supplier_name: supplier for supplier in quote.suppliers}
        recommended = suppliers.get(result.recommendation)
        if recommended is None:
            raise ApiError(502, "ai_supplier_unknown", "AI 推荐未能匹配当前报价中的供应商。")
        ranking = []
        seen: set[str] = set()
        for entry in result.ranking:
            supplier = suppliers.get(entry.name)
            if supplier is None or supplier.id in seen:
                continue
            seen.add(supplier.id)
            ranking.append({**entry.model_dump(mode="json"), "supplier_id": supplier.id})
        if not ranking:
            raise ApiError(502, "ai_ranking_invalid", "AI 排名未能匹配当前报价中的供应商。")
        return {
            "recommendation": result.recommendation,
            "recommended_supplier_id": recommended.id,
            "reason": result.reason,
            "ranking": ranking,
        }

    def create_quote(self, payload: QuoteCreateRequest, actor: str) -> QuoteJobView:
        job = self.repository.create_job(subject=payload.subject, currency=payload.currency, is_demo=payload.is_demo, actor=actor)
        self._audit.append(
            actor=actor,
            action="quote.create",
            object_type="steven_quote_job",
            object_id=job.id,
            before_after={"before": None, "after": {"subject": job.subject, "currency": job.currency, "recommended_supplier_id": None}},
        )
        return self._quote_view(job)

    def delete_quote(self, quote_id: str, actor: str) -> dict[str, str | bool]:
        job = self._require_job(quote_id)
        if job.status in {"approved", "exported"}:
            raise ApiError(409, "approved_record_delete_forbidden", "已批准或已导出的采购事项不可删除。")
        if self.repository.versions_for(quote_id):
            raise ApiError(409, "quote_has_export_versions", "存在导出版本的采购事项不可删除。")
        before = {"subject": job.subject, "status": job.status, "is_demo": job.is_demo}
        self.repository.delete_job(quote_id)
        self._audit.append(
            actor=actor,
            action="quote.delete",
            object_type="steven_quote_job",
            object_id=quote_id,
            before_after={"before": before, "after": None},
        )
        return {"id": quote_id, "deleted": True}

    def add_item(self, quote_id: str, payload: QuoteItemCreateRequest, actor: str) -> QuoteJobView:
        job = self._require_editable_job(quote_id)
        try:
            item = self.repository.add_item(
                quote_id,
                item_code=payload.item_code.strip(),
                item=payload.item.strip(),
                specification=payload.specification.strip(),
                qty=payload.qty,
                unit=payload.unit.strip(),
                actor=actor,
            )
        except ValueError as error:
            raise ApiError(409, "duplicate_item_code", "品项编码不得重复。", {"item_code": payload.item_code}) from error
        self.repository.touch_job(job, actor)
        self._refresh_status(job)
        self._audit.append(
            actor=actor,
            action="quote.item_write",
            object_type="steven_quote_item",
            object_id=item.id,
            before_after={"before": None, "after": {"quote_id": quote_id, "qty": str(item.qty)}},
        )
        return self._quote_view(job)

    def add_supplier(self, quote_id: str, payload: QuoteSupplierCreateRequest, actor: str) -> QuoteJobView:
        job = self._require_editable_job(quote_id)
        try:
            supplier = self.repository.add_supplier(
                quote_id,
                supplier_code=payload.supplier_code.strip(),
                supplier_name=payload.supplier_name.strip(),
                currency=payload.currency,
                valid_until=payload.valid_until,
                freight=payload.freight,
                tax=payload.tax,
                actor=actor,
            )
        except ValueError as error:
            code = str(error)
            raise ApiError(409, code, "供应商编码或名称不得重复。", {"supplier_code": payload.supplier_code}) from error
        self.repository.touch_job(job, actor)
        self._refresh_status(job)
        self._audit.append(
            actor=actor,
            action="quote.supplier_write",
            object_type="steven_quote_supplier",
            object_id=supplier.id,
            before_after={"before": None, "after": {"quote_id": quote_id, "currency": supplier.currency, "freight": str(supplier.freight), "tax": str(supplier.tax)}},
        )
        return self._quote_view(job)

    def reuse_supplier(self, quote_id: str, payload: QuoteSupplierReuseRequest, actor: str) -> QuoteJobView:
        job = self._require_editable_job(quote_id)
        history = self.repository.get_supplier_history(payload.supplier_code, payload.supplier_name)
        if history is None:
            raise ApiError(404, "supplier_history_not_found", "未找到可复用的已批准历史供应商。")
        historical_items = {item["item_code"]: item for item in history["items"]}
        unknown_codes = [code for code in payload.item_codes if code not in historical_items]
        if unknown_codes:
            raise ApiError(
                422,
                "supplier_history_item_invalid",
                "所选品项不属于该供应商的已批准历史报价。",
                {"item_codes": unknown_codes},
            )
        try:
            supplier = self.repository.add_supplier(
                quote_id,
                supplier_code=history["supplier_code"],
                supplier_name=history["supplier_name"],
                currency=job.currency,
                valid_until=payload.valid_until,
                freight=Decimal("0"),
                tax=Decimal("0"),
                actor=actor,
            )
            reused_item_ids = []
            for item_code in payload.item_codes:
                source = historical_items[item_code]
                item = self.repository.add_item(
                    quote_id,
                    item_code=source["item_code"],
                    item=source["item"],
                    specification=source["specification"],
                    qty=source["qty"],
                    unit=source["unit"],
                    actor=actor,
                )
                reused_item_ids.append(item.id)
        except ValueError as error:
            code = str(error)
            if code.startswith("duplicate_supplier"):
                raise ApiError(409, code, "供应商编码或名称不得重复。") from error
            raise ApiError(409, "duplicate_item_code", "所选历史品项与当前事项中的品项编码重复。") from error
        self.repository.touch_job(job, actor)
        self._refresh_status(job)
        self._audit.append(
            actor=actor,
            action="quote.supplier_reuse",
            object_type="steven_quote_job",
            object_id=quote_id,
            before_after={
                "before": None,
                "after": {
                    "supplier_id": supplier.id,
                    "supplier_code": supplier.supplier_code,
                    "reused_item_ids": reused_item_ids,
                    "reused_item_codes": payload.item_codes,
                    "prices_reused": False,
                },
            },
        )
        return self._quote_view(job)

    def add_offer(self, quote_id: str, payload: QuoteOfferLineCreateRequest, actor: str) -> QuoteJobView:
        job = self._require_editable_job(quote_id)
        supplier = self.repository.get_supplier(payload.quote_supplier_id)
        item = self.repository.get_item(payload.quote_item_id)
        if supplier is None or supplier.quote_job_id != quote_id:
            raise ApiError(422, "unknown_supplier", "报价供应商不属于当前采购事项。", {"supplier_id": payload.quote_supplier_id})
        if item is None or item.quote_job_id != quote_id:
            raise ApiError(422, "unknown_item", "报价品项不属于当前采购事项。", {"item_id": payload.quote_item_id})
        try:
            offer = self.repository.add_offer(
                supplier_id=supplier.id,
                item_id=item.id,
                unit_price=payload.unit_price,
                remark=payload.remark.strip(),
                actor=actor,
            )
        except ValueError as error:
            raise ApiError(
                409,
                "duplicate_supplier_item",
                "同一供应商与品项只能保存一条报价。",
                {"quote_supplier_id": supplier.id, "quote_item_id": item.id},
            ) from error
        self.repository.touch_job(job, actor)
        self._refresh_status(job)
        self._audit.append(
            actor=actor,
            action="quote.offer_line_write",
            object_type="steven_quote_offer_line",
            object_id=offer.id,
            before_after={"before": None, "after": {"unit_price": str(offer.unit_price), "line_total": str(offer.line_total)}},
        )
        return self._quote_view(job)

    def precheck_import(self, *, quote_id: str, filename: str, content: bytes, actor: str) -> QuoteImportPreview:
        job = self._require_editable_job(quote_id)
        parsed = self._parser.parse(filename, content, job.currency)
        import hashlib

        digest = hashlib.sha256(content).hexdigest()
        batch = self.repository.save_import_batch(
            quote_id=quote_id,
            actor=actor,
            filename=filename,
            sha256=digest,
            valid=parsed.valid,
            issues=parsed.issues,
            items=parsed.items,
            suppliers=parsed.suppliers,
            offers=parsed.offers,
        )
        self._audit.append(
            actor=actor,
            action="quote.import_precheck",
            object_type="steven_quote_import_batch",
            object_id=batch.id,
            before_after={"before": None, "after": {"valid": batch.valid, "filename": filename, "issue_count": len(batch.issues)}},
        )
        return QuoteImportPreview(
            batch_id=batch.id,
            quote_id=quote_id,
            filename=filename,
            sha256=digest,
            valid=batch.valid,
            item_count=len(parsed.items),
            supplier_count=len(parsed.suppliers),
            offer_count=len(parsed.offers),
            expected_offer_count=len(parsed.items) * len(parsed.suppliers),
            issues=parsed.issues,
        )

    def confirm_import(self, quote_id: str, batch_id: str, actor: str) -> QuoteJobView:
        job = self._require_editable_job(quote_id)
        batch = self.repository.get_import_batch(batch_id)
        if batch is None or batch.quote_id != quote_id:
            raise ApiError(404, "import_batch_not_found", "未找到导入预检批次。", {"batch_id": batch_id})
        if not batch.valid:
            raise ApiError(409, "import_has_errors", "导入预检仍有阻断错误，不能确认写入。", {"issues": batch.issues})
        if batch.confirmed:
            raise ApiError(409, "import_already_confirmed", "该导入批次已经人工确认写入。", {"batch_id": batch_id})
        if not self.repository.import_batch_integrity_valid(batch):
            raise ApiError(409, "import_payload_hash_mismatch", "导入批次内容校验失败，禁止写入。", {"batch_id": batch_id})
        if self.repository.items_for(quote_id) or self.repository.suppliers_for(quote_id) or self.repository.offers_for(quote_id):
            raise ApiError(409, "quote_not_empty", "为避免覆盖或重复，标准导入只允许写入空白采购事项。")

        item_ids: dict[str, str] = {}
        supplier_ids: dict[str, str] = {}
        for item in batch.items:
            record = self.repository.add_item(quote_id, actor=actor, **item)
            item_ids[item["item_code"]] = record.id
        for supplier in batch.suppliers:
            record = self.repository.add_supplier(quote_id, actor=actor, **supplier)
            supplier_ids[supplier["supplier_code"]] = record.id
        for offer in batch.offers:
            self.repository.add_offer(
                supplier_id=supplier_ids[offer["supplier_code"]],
                item_id=item_ids[offer["item_code"]],
                unit_price=offer["unit_price"],
                remark=offer["remark"],
                actor=actor,
            )
        self.repository.confirm_import_batch(batch, actor)
        self.repository.touch_job(job, actor)
        self._refresh_status(job)
        self._audit.append(
            actor=actor,
            action="quote.import_confirm",
            object_type="steven_quote_job",
            object_id=quote_id,
            before_after={"before": {"item_count": 0, "supplier_count": 0, "offer_count": 0}, "after": {"item_count": len(batch.items), "supplier_count": len(batch.suppliers), "offer_count": len(batch.offers), "batch_id": batch.id}},
        )
        return self._quote_view(job)

    def save_recommendation(self, quote_id: str, payload: QuoteRecommendationRequest, actor: str) -> QuoteJobView:
        job = self._require_editable_job(quote_id)
        comparison = self._calculate(job)
        if not comparison["comparison_allowed"]:
            raise ApiError(409, "comparison_blocked", "报价不完整或币种不一致，不能保存推荐供应商。", {"reasons": comparison["blocking_reasons"]})
        supplier = self.repository.get_supplier(payload.recommended_supplier_id)
        if supplier is None or supplier.quote_job_id != quote_id:
            raise ApiError(422, "unknown_supplier", "推荐供应商不属于当前采购事项。")
        is_non_lowest = supplier.id != comparison["lowest_supplier_id"]
        reason = payload.non_lowest_reason.strip()
        opinion = payload.approval_opinion.strip()
        if is_non_lowest and (not reason or not opinion):
            raise ApiError(
                422,
                "non_lowest_justification_required",
                "推荐非最低价供应商时，必须同时填写非最低价理由和审批意见。",
                {"non_lowest_reason_required": True, "approval_opinion_required": True},
            )
        before = {
            "recommended_supplier_id": job.recommended_supplier_id,
            "non_lowest_reason": job.non_lowest_reason,
            "approval_opinion": job.approval_opinion,
        }
        job.recommended_supplier_id = supplier.id
        job.non_lowest_reason = reason or None
        job.approval_opinion = opinion or None
        self.repository.touch_job(job, actor)
        self._audit.append(
            actor=actor,
            action="quote.recommend",
            object_type="steven_quote_job",
            object_id=quote_id,
            before_after={"before": before, "after": {"recommended_supplier_id": supplier.id, "is_non_lowest": is_non_lowest, "non_lowest_reason": reason or None, "approval_opinion": opinion or None}},
        )
        return self._quote_view(job)

    def submit_approval(self, quote_id: str, actor: str) -> QuoteApprovalView:
        job = self._require_editable_job(quote_id)
        comparison = self._calculate(job)
        if not comparison["comparison_allowed"]:
            raise ApiError(409, "comparison_blocked", "报价不完整或币种不一致，不能提交审批。", {"reasons": comparison["blocking_reasons"]})
        if not job.recommended_supplier_id:
            raise ApiError(409, "recommendation_required", "推荐供应商必须由人工填写后才能提交审批。")
        if job.recommended_supplier_id != comparison["lowest_supplier_id"] and (not job.non_lowest_reason or not job.approval_opinion):
            raise ApiError(422, "non_lowest_justification_required", "非最低价理由和审批意见两项缺一不可。")
        approval = self.repository.create_approval(quote_id, actor)
        job.approval_id = approval.id
        job.status = "pending_approval"
        self.repository.touch_job(job, actor)
        self._audit.append(
            actor=actor,
            action="quote.submit",
            object_type="steven_quote_job",
            object_id=quote_id,
            before_after={"before": {"status": "ready_for_review"}, "after": {"status": job.status, "approval_id": approval.id}},
        )
        return QuoteApprovalView(approval_id=approval.id, status="pending", quote=self._quote_view(job))

    def approve(self, quote_id: str, actor: str, opinion: str) -> QuoteApprovalView:
        job = self._require_job(quote_id)
        if not job.approval_id:
            raise ApiError(409, "approval_not_submitted", "采购比价尚未提交审批。")
        approval = self.repository.get_approval(job.approval_id)
        if approval is None or approval.status != "pending":
            raise ApiError(409, "approval_closed", "审批任务不存在或已经处理。")
        if approval.submitted_by == actor:
            raise ApiError(403, "self_approval_forbidden", "提交人不得审批本人任务。")
        approval.status = "approved"
        approval.opinion = opinion
        approval.decided_by = actor
        approval.updated_at = datetime.now(timezone.utc)
        self.repository.save_approval(approval)
        job.status = "approved"
        self.repository.touch_job(job, actor)
        self._audit.append(
            actor=actor,
            action="quote.approve",
            object_type="steven_quote_job",
            object_id=quote_id,
            before_after={"before": {"status": "pending_approval"}, "after": {"status": "approved", "opinion": opinion}},
        )
        return QuoteApprovalView(approval_id=approval.id, status="approved", quote=self._quote_view(job))

    def reject(self, quote_id: str, actor: str, opinion: str) -> QuoteApprovalView:
        job = self._require_job(quote_id)
        if not job.approval_id:
            raise ApiError(409, "approval_not_submitted", "采购比价尚未提交审批。")
        approval = self.repository.get_approval(job.approval_id)
        if approval is None or approval.status != "pending":
            raise ApiError(409, "approval_closed", "审批任务不存在或已经处理。")
        if approval.submitted_by == actor:
            raise ApiError(403, "self_approval_forbidden", "提交人不得退回本人任务。")
        approval.status = "rejected"
        approval.opinion = opinion
        approval.decided_by = actor
        approval.updated_at = datetime.now(timezone.utc)
        self.repository.save_approval(approval)
        job.status = "ready_for_review"
        self.repository.touch_job(job, actor)
        self._audit.append(
            actor=actor,
            action="quote.reject",
            object_type="steven_quote_job",
            object_id=quote_id,
            before_after={"before": {"status": "pending_approval"}, "after": {"status": "ready_for_review", "opinion": opinion}},
        )
        return QuoteApprovalView(approval_id=approval.id, status="rejected", quote=self._quote_view(job))

    def export(self, quote_id: str, actor: str) -> QuoteExportView:
        job = self._require_job(quote_id)
        if job.status not in {"approved", "exported"}:
            raise ApiError(409, "approval_required", "采购比价未获人工批准，不能正式导出。", {"status": job.status})
        comparison = self._calculate(job)
        if not comparison["comparison_allowed"]:
            raise ApiError(409, "comparison_blocked", "报价不完整或币种不一致，不能导出正式比价。", {"reasons": comparison["blocking_reasons"]})
        items = self.repository.items_for(quote_id)
        suppliers = self.repository.suppliers_for(quote_id)
        offers = self.repository.offers_for(quote_id)
        filename_template = self._storage.filename_template(job.subject)
        storage_template = self._storage.storage_template(quote_id, filename_template)
        version = self.repository.reserve_version(quote_id, actor, filename_template, storage_template)
        try:
            result = self._storage.publish(
                quote_id=quote_id,
                version_number=version.version_number,
                filename=version.filename,
                render=lambda target: self._exporter.render_to(
                    target=target,
                    quote=job,
                    items=items,
                    suppliers=suppliers,
                    offers=offers,
                    comparison=comparison,
                ),
            )
        except Exception as error:
            self.repository.mark_version_failed(version.id, f"{type(error).__name__}: {error}")
            code = "version_conflict" if isinstance(error, FileExistsError) else "export_failed"
            status_code = 409 if isinstance(error, FileExistsError) else 500
            raise ApiError(
                status_code,
                code,
                "导出失败，版本号已保留且不会复用。",
                {"version_number": version.version_number},
            ) from error
        version = self.repository.mark_version_ready(
            version.id,
            sha256=result.sha256,
            size_bytes=result.size_bytes,
            published_at=datetime.now(timezone.utc),
        )
        before = {"status": job.status}
        job.status = "exported"
        self.repository.touch_job(job, actor)
        self._audit.append(
            actor=actor,
            action="quote.export",
            object_type="steven_quote_job",
            object_id=quote_id,
            before_after={
                "before": before,
                "after": {
                    "status": job.status,
                    "version_number": version.version_number,
                    "storage_key": result.storage_key,
                    "sha256": result.sha256,
                },
            },
        )
        return QuoteExportView(quote=self._quote_view(job), version=self._version_view(version))

    def list_versions(self, quote_id: str) -> list[QuoteVersionView]:
        self._require_job(quote_id)
        return [self._version_view(version) for version in self.repository.versions_for(quote_id)]

    def list_audit_events(self, quote_id: str) -> list[dict]:
        self._require_job(quote_id)
        return self._audit.list_for_object(quote_id)

    def version_file(self, quote_id: str, version_number: int) -> Path:
        self._require_job(quote_id)
        for version in self.repository.versions_for(quote_id):
            if version.version_number == version_number:
                if version.status != "ready":
                    raise ApiError(409, "version_not_ready", "导出版本尚未完成发布。", {"status": version.status})
                path = self._storage.resolve(version.storage_key)
                if not path.is_file():
                    raise ApiError(404, "file_not_found", "导出文件不存在。")
                return path
        raise ApiError(404, "version_not_found", "未找到导出版本。", {"version_number": version_number})

    def _refresh_status(self, job: QuoteJobRecord) -> None:
        if job.status in {"pending_approval", "approved", "exported"}:
            return
        comparison = self._calculate(job)
        job.status = "ready_for_review" if comparison["comparison_allowed"] else "incomplete"

    def _calculate(self, job: QuoteJobRecord) -> dict:
        items = self.repository.items_for(job.id)
        suppliers = self.repository.suppliers_for(job.id)
        offers = self.repository.offers_for(job.id)
        item_ids = {item.id for item in items}
        offers_by_supplier: dict[str, list] = {supplier.id: [] for supplier in suppliers}
        for offer in offers:
            if offer.quote_item_id in item_ids and offer.quote_supplier_id in offers_by_supplier:
                offers_by_supplier[offer.quote_supplier_id].append(offer)
        expected = len(items) * len(suppliers)
        actual_pairs = {(offer.quote_supplier_id, offer.quote_item_id) for offer in offers}
        blocking_reasons: list[str] = []
        if len(actual_pairs) != expected or any(len({offer.quote_item_id for offer in offers_by_supplier[supplier.id]}) != len(items) for supplier in suppliers):
            blocking_reasons.append(f"报价不完整：应有 {expected} 条唯一明细，实际 {len(actual_pairs)} 条。")
        currencies = {supplier.currency for supplier in suppliers}
        if suppliers and (len(currencies) != 1 or currencies != {job.currency}):
            blocking_reasons.append("供应商币种与采购事项币种不一致。")
        if not items or not suppliers:
            blocking_reasons.append("采购品项或供应商尚未录入。")
        warnings: list[str] = []
        ranking: list[dict] = []
        for supplier in suppliers:
            subtotal = sum((offer.line_total for offer in offers_by_supplier[supplier.id]), Decimal("0"))
            supplier.subtotal = subtotal
            supplier.total = subtotal + supplier.freight + supplier.tax
            if supplier.valid_until < date.today():
                warnings.append(f"{supplier.supplier_name} 的报价已过期。")
        comparison_allowed = not blocking_reasons
        if comparison_allowed:
            sorted_suppliers = sorted(suppliers, key=lambda supplier: (supplier.total, supplier.supplier_name))
            ranking = [
                {
                    "rank": index,
                    "supplier_id": supplier.id,
                    "supplier_name": supplier.supplier_name,
                    "subtotal": supplier.subtotal,
                    "freight": supplier.freight,
                    "tax": supplier.tax,
                    "total": supplier.total,
                    "expired": supplier.valid_until < date.today(),
                }
                for index, supplier in enumerate(sorted_suppliers, start=1)
            ]
        lowest_supplier_id = ranking[0]["supplier_id"] if ranking else None
        lowest_supplier_name = ranking[0]["supplier_name"] if ranking else None
        recommended_supplier = self.repository.get_supplier(job.recommended_supplier_id) if job.recommended_supplier_id else None
        return {
            "comparison_allowed": comparison_allowed,
            "expected_offer_count": expected,
            "actual_offer_count": len(actual_pairs),
            "blocking_reasons": blocking_reasons,
            "warnings": warnings,
            "ranking": ranking,
            "lowest_supplier_id": lowest_supplier_id,
            "lowest_supplier_name": lowest_supplier_name,
            "recommended_supplier_name": recommended_supplier.supplier_name if recommended_supplier else None,
        }

    def _quote_view(self, job: QuoteJobRecord) -> QuoteJobView:
        comparison = self._calculate(job)
        if job.status not in {"pending_approval", "approved", "exported"}:
            job.status = "ready_for_review" if comparison["comparison_allowed"] else ("draft" if not self.repository.items_for(job.id) and not self.repository.suppliers_for(job.id) else "incomplete")
        return QuoteJobView(
            id=job.id,
            subject=job.subject,
            currency=job.currency,
            status=job.status,
            is_demo=job.is_demo,
            demo_label=job.demo_label,
            recommended_supplier_id=job.recommended_supplier_id,
            non_lowest_reason=job.non_lowest_reason,
            approval_opinion=job.approval_opinion,
            approval_id=job.approval_id,
            items=[
                {"id": item.id, "item_code": item.item_code, "item": item.item, "specification": item.specification, "qty": item.qty, "unit": item.unit}
                for item in self.repository.items_for(job.id)
            ],
            suppliers=[
                {
                    "id": supplier.id,
                    "supplier_code": supplier.supplier_code,
                    "supplier_name": supplier.supplier_name,
                    "currency": supplier.currency,
                    "valid_until": supplier.valid_until,
                    "freight": supplier.freight,
                    "tax": supplier.tax,
                    "subtotal": supplier.subtotal,
                    "total": supplier.total,
                    "expired": supplier.valid_until < date.today(),
                }
                for supplier in self.repository.suppliers_for(job.id)
            ],
            offer_lines=[
                {
                    "id": offer.id,
                    "quote_supplier_id": offer.quote_supplier_id,
                    "quote_item_id": offer.quote_item_id,
                    "unit_price": offer.unit_price,
                    "line_total": offer.line_total,
                    "remark": offer.remark,
                }
                for offer in self.repository.offers_for(job.id)
            ],
            comparison=comparison,
            created_at=job.created_at,
            updated_at=job.updated_at,
            created_by=job.created_by,
            updated_by=job.updated_by,
        )

    @staticmethod
    def _version_view(version: QuoteVersionRecord) -> QuoteVersionView:
        return QuoteVersionView(
            id=version.id,
            version_number=version.version_number,
            filename=version.filename,
            storage_key=version.storage_key,
            sha256=version.sha256,
            status=version.status,
            mime_type=version.mime_type,
            size_bytes=version.size_bytes,
            failure_reason=version.failure_reason,
            created_at=version.created_at,
            created_by=version.created_by,
        )

    def _require_job(self, quote_id: str) -> QuoteJobRecord:
        job = self.repository.get_job(quote_id)
        if job is None:
            raise ApiError(404, "quote_not_found", "未找到采购比价事项。", {"id": quote_id})
        return job

    def _require_editable_job(self, quote_id: str) -> QuoteJobRecord:
        job = self._require_job(quote_id)
        if job.status in {"pending_approval", "approved", "exported"}:
            raise ApiError(409, "quote_locked", "采购比价已提交审批或导出，当前不可修改。", {"status": job.status})
        return job
