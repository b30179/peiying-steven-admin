from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.exc import IntegrityError

from app.core.api_response import ApiError
from app.modules.steven.quote_excel import LocalAppendOnlyQuoteStorage, PublishedQuoteFile, QuoteExcelExporter, QuoteImportParser
from app.modules.steven.quote_schemas import (
    QuoteApprovalRequest,
    QuoteCreateRequest,
    QuoteImportPreview,
    QuoteItemCreateRequest,
    QuoteOfferLineCreateRequest,
    QuoteRecommendationRequest,
    QuoteSupplierCreateRequest,
    QuoteSupplierReuseRequest,
)
from app.modules.steven.quote_service import StevenQuoteService
from app.modules.steven.quote_uow import QuoteUnitOfWork


@dataclass(frozen=True)
class ReservedExport:
    quote_id: str
    version_id: str
    version_number: int
    filename: str
    quote: object
    items: list
    suppliers: list
    offers: list
    comparison: dict


class StevenQuoteApplicationService:
    def __init__(self, unit_of_work: QuoteUnitOfWork, parser: QuoteImportParser, exporter: QuoteExcelExporter, storage: LocalAppendOnlyQuoteStorage) -> None:
        self._unit_of_work = unit_of_work
        self._parser = parser
        self._exporter = exporter
        self._storage = storage

    def _service(self, transaction) -> StevenQuoteService:
        return StevenQuoteService(transaction.repository, transaction.audit, self._parser, self._exporter, self._storage)

    def _run(self, callback, *, quote_id: str | None = None, batch_id: str | None = None, approval_id: str | None = None):
        try:
            with self._unit_of_work.begin(quote_id=quote_id, batch_id=batch_id, approval_id=approval_id) as transaction:
                return callback(self._service(transaction))
        except IntegrityError as error:
            raise ApiError(409, "concurrent_write_conflict", "数据已被其他请求更新，请刷新后重试。") from error
        except ValueError as error:
            code = str(error)
            if code in {"import_already_confirmed", "approval_closed", "version_not_reserved"}:
                raise ApiError(409, code, "操作已由其他请求完成，请刷新后重试。") from error
            raise

    def list_quotes(self):
        return self._run(lambda service: service.list_quotes())

    def search_suppliers(self, query: str, limit: int):
        return self._run(lambda service: service.search_suppliers(query, limit))

    def get_quote(self, quote_id: str):
        return self._run(lambda service: service.get_quote(quote_id), quote_id=quote_id)

    def recommend_supplier(self, quote_id: str, ai_assist):
        return self._run(lambda service: service.recommend_supplier(quote_id, ai_assist), quote_id=quote_id)

    def create_quote(self, payload: QuoteCreateRequest, actor: str):
        return self._run(lambda service: service.create_quote(payload, actor))

    def delete_quote(self, quote_id: str, actor: str):
        return self._run(lambda service: service.delete_quote(quote_id, actor), quote_id=quote_id)

    def add_item(self, quote_id: str, payload: QuoteItemCreateRequest, actor: str):
        return self._run(lambda service: service.add_item(quote_id, payload, actor), quote_id=quote_id)

    def add_supplier(self, quote_id: str, payload: QuoteSupplierCreateRequest, actor: str):
        return self._run(lambda service: service.add_supplier(quote_id, payload, actor), quote_id=quote_id)

    def reuse_supplier(self, quote_id: str, payload: QuoteSupplierReuseRequest, actor: str):
        return self._run(lambda service: service.reuse_supplier(quote_id, payload, actor), quote_id=quote_id)

    def add_offer(self, quote_id: str, payload: QuoteOfferLineCreateRequest, actor: str):
        return self._run(lambda service: service.add_offer(quote_id, payload, actor), quote_id=quote_id)

    def precheck_import(self, *, quote_id: str, filename: str, content: bytes, actor: str) -> QuoteImportPreview:
        return self._run(lambda service: service.precheck_import(quote_id=quote_id, filename=filename, content=content, actor=actor), quote_id=quote_id)

    def confirm_import(self, quote_id: str, batch_id: str, actor: str):
        return self._run(lambda service: service.confirm_import(quote_id, batch_id, actor), quote_id=quote_id, batch_id=batch_id)

    def save_recommendation(self, quote_id: str, payload: QuoteRecommendationRequest, actor: str):
        return self._run(lambda service: service.save_recommendation(quote_id, payload, actor), quote_id=quote_id)

    def submit_approval(self, quote_id: str, actor: str):
        return self._run(lambda service: service.submit_approval(quote_id, actor), quote_id=quote_id)

    def approve(self, quote_id: str, actor: str, opinion: str):
        approval_id = self._run(lambda service: service.get_quote(quote_id).approval_id, quote_id=quote_id)
        return self._run(lambda service: service.approve(quote_id, actor, opinion), quote_id=quote_id, approval_id=approval_id)

    def reject(self, quote_id: str, actor: str, opinion: str):
        approval_id = self._run(lambda service: service.get_quote(quote_id).approval_id, quote_id=quote_id)
        return self._run(lambda service: service.reject(quote_id, actor, opinion), quote_id=quote_id, approval_id=approval_id)

    def export(self, quote_id: str, actor: str):
        reservation = self._reserve_export(quote_id, actor)
        try:
            published = self._storage.publish(
                quote_id=quote_id,
                version_number=reservation.version_number,
                filename=reservation.filename,
                render=lambda target: self._exporter.render_to(
                    target=target,
                    quote=reservation.quote,
                    items=reservation.items,
                    suppliers=reservation.suppliers,
                    offers=reservation.offers,
                    comparison=reservation.comparison,
                ),
            )
        except Exception as error:
            self._fail_export(
                quote_id,
                reservation.version_id,
                actor,
                f"{type(error).__name__}: {error}",
                "quote.export_failed",
            )
            raise ApiError(500, "export_failed", "导出失败，版本号已保留且不会复用。", {"version_number": reservation.version_number}) from error
        return self._complete_export(reservation, published, actor)

    def _reserve_export(self, quote_id: str, actor: str) -> ReservedExport:
        def reserve(service: StevenQuoteService) -> ReservedExport:
            job = service._require_job(quote_id)
            if job.status not in {"approved", "exported"}:
                raise ApiError(409, "approval_required", "采购比价未获人工批准，不能正式导出。", {"status": job.status})
            comparison = service._calculate(job)
            if not comparison["comparison_allowed"]:
                raise ApiError(409, "comparison_blocked", "报价不完整或币种不一致，不能导出正式比价。")
            filename_template = self._storage.filename_template(job.subject)
            version = service.repository.reserve_version(
                quote_id,
                actor,
                filename_template,
                self._storage.storage_template(quote_id, filename_template),
            )
            service._audit.append(
                actor=actor,
                action="quote.export_reserved",
                object_type="steven_quote_version",
                object_id=version.id,
                before_after={"before": None, "after": {"quote_id": quote_id, "version_number": version.version_number, "status": "reserved"}},
            )
            return ReservedExport(
                quote_id, version.id, version.version_number, version.filename, job,
                service.repository.items_for(quote_id), service.repository.suppliers_for(quote_id),
                service.repository.offers_for(quote_id), comparison,
            )
        return self._run(reserve, quote_id=quote_id)

    def _complete_export(self, reservation: ReservedExport, published: PublishedQuoteFile, actor: str):
        def complete(service: StevenQuoteService):
            version = service.repository.mark_version_ready(
                reservation.version_id,
                sha256=published.sha256,
                size_bytes=published.size_bytes,
                published_at=datetime.now(timezone.utc),
            )
            job = service._require_job(reservation.quote_id)
            before = {"status": job.status}
            job.status = "exported"
            service.repository.touch_job(job, actor)
            service._audit.append(
                actor=actor,
                action="quote.export",
                object_type="steven_quote_job",
                object_id=reservation.quote_id,
                before_after={"before": before, "after": {"status": "exported", "version_number": version.version_number, "storage_key": version.storage_key, "sha256": published.sha256}},
            )
            from app.modules.steven.quote_schemas import QuoteExportView
            return QuoteExportView(quote=service._quote_view(job), version=service._version_view(version))
        return self._run(complete, quote_id=reservation.quote_id)

    def list_versions(self, quote_id: str):
        return self._run(lambda service: service.list_versions(quote_id), quote_id=quote_id)

    def reconcile_export(self, quote_id: str, version_id: str, actor: str):
        version = self._run(lambda service: service.repository.get_version_by_id(version_id), quote_id=quote_id)
        if version is None or version.quote_id != quote_id:
            raise ApiError(404, "version_not_found", "未找到导出版本。")
        if version.status != "reserved":
            raise ApiError(409, "version_not_reserved", "仅可对账 reserved 状态的导出版本。", {"status": version.status})
        try:
            published = self._storage.inspect_existing(version.storage_key)
        except FileNotFoundError as error:
            self._fail_export(
                quote_id,
                version_id,
                actor,
                "published_file_missing_during_reconciliation",
                "quote.export_reconciliation_failed",
            )
            raise ApiError(409, "published_file_missing", "预留版本未找到已发布文件，已标记失败且版本号不复用。") from error
        except Exception as error:
            self._fail_export(
                quote_id,
                version_id,
                actor,
                f"published_file_invalid_during_reconciliation: {type(error).__name__}",
                "quote.export_reconciliation_failed",
            )
            raise ApiError(409, "published_file_invalid", "预留版本对应文件无法通过可读性校验，已标记失败且版本号不复用。") from error

        def complete(service: StevenQuoteService):
            ready = service.repository.mark_version_ready(
                version_id,
                sha256=published.sha256,
                size_bytes=published.size_bytes,
                published_at=datetime.now(timezone.utc),
            )
            service._audit.append(
                actor=actor,
                action="quote.export_reconciled",
                object_type="steven_quote_version",
                object_id=version_id,
                before_after={"before": {"status": "reserved"}, "after": {"quote_id": quote_id, "status": "ready", "sha256": published.sha256, "size_bytes": published.size_bytes}},
            )
            return service._version_view(ready)

        return self._run(complete, quote_id=quote_id)

    def _fail_export(self, quote_id: str, version_id: str, actor: str, reason: str, action: str):
        def fail(service: StevenQuoteService):
            version = service.repository.mark_version_failed(version_id, reason)
            service._audit.append(
                actor=actor,
                action=action,
                object_type="steven_quote_version",
                object_id=version_id,
                before_after={
                    "before": {"status": "reserved"},
                    "after": {"quote_id": quote_id, "status": "failed", "failure_reason": version.failure_reason},
                },
            )
            return version

        return self._run(fail, quote_id=quote_id)

    def list_audit_events(self, quote_id: str):
        return self._run(lambda service: service.list_audit_events(quote_id), quote_id=quote_id)

    def version_file(self, quote_id: str, version_number: int) -> Path:
        return self._run(lambda service: service.version_file(quote_id, version_number), quote_id=quote_id)
