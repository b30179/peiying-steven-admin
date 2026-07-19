from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from app.core.api_response import ApiError
from app.core.audit_context import current_request_id
from app.modules.platform.append_only_storage import LocalAppendOnlyFileStorage, PublishedFile
from app.modules.steven.tender_schemas import TenderTemplatePreviewRequest
from app.modules.steven.tender_service import StevenTenderService
from app.modules.steven.tender_word import TenderWordRenderer


@dataclass(frozen=True)
class ReservedTenderExport:
    tender_id: str
    version_id: str
    version_number: int
    filename: str
    storage_key: str
    job: object
    suppliers: list
    rendered_body: str
    export_batch_id: str | None = None
    supplier_id: str | None = None
    supplier_name_snapshot: str | None = None


class StevenTenderApplicationService:
    def __init__(self, unit_of_work, renderer: TenderWordRenderer, storage: LocalAppendOnlyFileStorage) -> None:
        self._unit_of_work = unit_of_work
        self._renderer = renderer
        self._storage = storage

    def _service(self, transaction) -> StevenTenderService:
        return StevenTenderService(transaction.repository, transaction.audit)

    def _run(self, callback, *, tender_id: str | None = None, version_id: str | None = None):
        try:
            with self._unit_of_work.begin(tender_id=tender_id, version_id=version_id) as transaction:
                return callback(self._service(transaction))
        except IntegrityError as error:
            constraint = getattr(getattr(error, "orig", None), "diag", None)
            name = getattr(constraint, "constraint_name", "") if constraint else ""
            if name == "uq_steven_tender_supplier_name":
                raise ApiError(409, "duplicate_supplier_name", "同一文书事项中供应商名称不得重复。") from error
            if name == "uq_steven_tender_jobs_document_number":
                raise ApiError(409, "duplicate_document_number", "文书编号已存在。") from error
            raise ApiError(409, "concurrent_write_conflict", "数据已被其他请求更新，请刷新后重试。") from error
        except ValueError as error:
            if str(error) in {"version_not_reserved"}:
                raise ApiError(409, str(error), "导出版本状态已变化，请刷新后重试。") from error
            raise

    def ensure_demo_template(self, actor: str):
        return self._run(lambda service: service.ensure_demo_template(actor))

    def list_templates(self):
        return self._run(lambda service: service.list_templates())

    def create_template(self, payload, actor: str):
        return self._run(lambda service: service.create_template(payload, actor))

    def update_template(self, template_id: str, payload, actor: str):
        return self._run(lambda service: service.update_template(template_id, payload, actor))

    def delete_template(self, template_id: str, actor: str):
        return self._run(lambda service: service.delete_template(template_id, actor))

    def recommend_templates(self, query: str):
        return self._run(lambda service: service.recommend_templates(query))

    def preview_template(
        self,
        template_id: str,
        tender_id: str | None = None,
        draft: TenderTemplatePreviewRequest | None = None,
    ):
        return self._run(
            lambda service: service.preview_template(template_id, tender_id, draft),
            tender_id=tender_id,
        )

    def list_tenders(self):
        return self._run(lambda service: service.list_tenders())

    def get_tender(self, tender_id: str):
        return self._run(lambda service: service.get_tender(tender_id), tender_id=tender_id)

    def create_tender(self, payload, actor: str):
        return self._run(lambda service: service.create_tender(payload, actor))

    def delete_tender(self, tender_id: str, actor: str):
        return self._run(lambda service: service.delete_tender(tender_id, actor), tender_id=tender_id)

    def update_tender(self, tender_id: str, payload, actor: str):
        return self._run(lambda service: service.update_tender(tender_id, payload, actor), tender_id=tender_id)

    def preview(self, tender_id: str, actor: str):
        return self._run(lambda service: service.preview(tender_id, actor), tender_id=tender_id)

    def draft_bytes(self, tender_id: str, actor: str) -> tuple[str, bytes]:
        preview = self.preview(tender_id, actor)
        tender = self._run(lambda service: service._require_job(tender_id), tender_id=tender_id)
        suppliers = self._run(lambda service: service.repository.suppliers_for(tender_id), tender_id=tender_id)
        filename = f"{date.today():%Y%m%d}_草稿_{self._storage.safe_segment(tender.title)}.docx"
        return filename, self._renderer.render_bytes(
            job=tender,
            suppliers=suppliers,
            rendered_body=preview.tender.rendered_body or "",
            formal=False,
        )

    def submit(self, tender_id: str, actor: str):
        result = self._run(lambda service: service.submit(tender_id, actor), tender_id=tender_id)
        if result.status == "draft_error":
            raise ApiError(
                409,
                "draft_not_ready",
                "存在未替换变量，不能提交审批。",
                {"variables": result.unresolved_variables, "status": result.status},
            )
        return result

    def approve(self, tender_id: str, actor: str, opinion: str):
        return self._run(lambda service: service.approve(tender_id, actor, opinion), tender_id=tender_id)

    def return_for_revision(self, tender_id: str, actor: str, opinion: str):
        return self._run(lambda service: service.return_for_revision(tender_id, actor, opinion), tender_id=tender_id)

    def export(self, tender_id: str, actor: str):
        reservation = self._reserve_export(tender_id, actor)
        try:
            published = self._storage.publish(
                object_id=tender_id,
                version_number=reservation.version_number,
                filename=reservation.filename,
                render=lambda target: self._renderer.render_to(
                    target,
                    job=reservation.job,
                    suppliers=reservation.suppliers,
                    rendered_body=reservation.rendered_body,
                    formal=True,
                    version_number=reservation.version_number,
                ),
            )
        except Exception as error:
            self._fail_export(tender_id, reservation.version_id, actor, f"{type(error).__name__}: {error}")
            raise ApiError(
                500,
                "export_failed",
                "正式 Word 导出失败，版本号已保留且不会复用。",
                {"version_number": reservation.version_number},
            ) from error
        return self._complete_export(reservation, published, actor)

    def batch_export(self, tender_id: str, supplier_ids: list[str], actor: str):
        batch_id, reservations = self._reserve_batch_exports(tender_id, supplier_ids, actor)
        versions = []
        failed_versions: list[int] = []
        for reservation in reservations:
            try:
                published = self._storage.publish(
                    object_id=tender_id,
                    version_number=reservation.version_number,
                    filename=reservation.filename,
                    render=lambda target, current=reservation: self._renderer.render_to(
                        target,
                        job=current.job,
                        suppliers=current.suppliers,
                        rendered_body=current.rendered_body,
                        formal=True,
                        version_number=current.version_number,
                    ),
                )
            except Exception as error:
                versions.append(
                    self._fail_export(
                        tender_id,
                        reservation.version_id,
                        actor,
                        f"{type(error).__name__}: {error}",
                    )
                )
                failed_versions.append(reservation.version_number)
                continue
            versions.append(self._complete_export(reservation, published, actor).version)

        result = self._complete_batch_export(tender_id, batch_id, versions, actor)
        if failed_versions:
            raise ApiError(
                500,
                "batch_export_failed",
                "部分正式 Word 生成失败；失败版本号已保留且不会复用。",
                {"batch_id": batch_id, "failed_versions": failed_versions},
            )
        return result

    def _reserve_export(self, tender_id: str, actor: str) -> ReservedTenderExport:
        def reserve(service: StevenTenderService):
            job = service._require_job(tender_id)
            if job.status != "approved":
                raise ApiError(409, "formal_export_forbidden", "仅已批准文书可生成正式 Word。", {"status": job.status})
            rendered, unresolved = service._render(job)
            if unresolved:
                raise ApiError(409, "draft_not_ready", "存在未替换变量，不能正式导出。", {"variables": unresolved})
            filename_template = f"{date.today():%Y%m%d}_正式文书_{self._storage.safe_segment(job.title)}_v{{version}}.docx"
            version = service.repository.reserve_version(
                tender_id,
                actor,
                filename_template,
                self._storage.storage_template(tender_id, filename_template),
            )
            service.audit.append(
                actor=actor,
                action="tender.export_reserved",
                object_type="steven_tender_job",
                object_id=tender_id,
                before_after={"before": None, "after": {"version_number": version.version_number, "status": "reserved"}},
            )
            return ReservedTenderExport(
                tender_id,
                version.id,
                version.version_number,
                version.filename,
                version.storage_key,
                job,
                service.repository.suppliers_for(tender_id),
                rendered,
            )
        return self._run(reserve, tender_id=tender_id)

    def _reserve_batch_exports(
        self,
        tender_id: str,
        supplier_ids: list[str],
        actor: str,
    ) -> tuple[str, list[ReservedTenderExport]]:
        def reserve(service: StevenTenderService):
            job = service._require_job(tender_id)
            if job.status != "approved":
                raise ApiError(409, "formal_export_forbidden", "仅已批准文书可生成正式 Word。", {"status": job.status})
            if len(supplier_ids) < 2 or len(supplier_ids) > 20:
                raise ApiError(422, "batch_supplier_count_invalid", "批量导出必须选择 2 至 20 名供应商。")
            if len(set(supplier_ids)) != len(supplier_ids):
                raise ApiError(422, "duplicate_supplier_selection", "批量导出不可重复选择同一供应商。")

            suppliers = service.repository.suppliers_for(tender_id)
            supplier_by_id = {item.id: item for item in suppliers}
            missing = [supplier_id for supplier_id in supplier_ids if supplier_id not in supplier_by_id]
            if missing:
                raise ApiError(
                    422,
                    "supplier_not_in_tender",
                    "所选供应商必须全部属于当前文书事项。",
                    {"invalid_supplier_count": len(missing)},
                )

            batch_id = str(uuid4())
            reservations: list[ReservedTenderExport] = []
            for supplier_id in supplier_ids:
                supplier = supplier_by_id[supplier_id]
                rendered, unresolved = service._render(job, [supplier])
                if unresolved:
                    raise ApiError(409, "draft_not_ready", "存在未替换变量，不能正式导出。", {"variables": unresolved})
                safe_supplier = self._storage.safe_segment(supplier.supplier_name)
                filename_template = (
                    f"{date.today():%Y%m%d}_正式文书_{self._storage.safe_segment(job.title)}_"
                    f"{safe_supplier}_v{{version}}.docx"
                )
                version = service.repository.reserve_version(
                    tender_id,
                    actor,
                    filename_template,
                    self._storage.storage_template(tender_id, filename_template),
                    export_batch_id=batch_id,
                    supplier_id=supplier.id,
                    supplier_name_snapshot=supplier.supplier_name,
                )
                reservations.append(
                    ReservedTenderExport(
                        tender_id=tender_id,
                        version_id=version.id,
                        version_number=version.version_number,
                        filename=version.filename,
                        storage_key=version.storage_key,
                        job=job,
                        suppliers=[supplier],
                        rendered_body=rendered,
                        export_batch_id=batch_id,
                        supplier_id=supplier.id,
                        supplier_name_snapshot=supplier.supplier_name,
                    )
                )
            service.audit.append(
                actor=actor,
                action="tender.batch_export_reserved",
                object_type="steven_tender_job",
                object_id=tender_id,
                before_after={
                    "before": None,
                    "after": {
                        "batch_id": batch_id,
                        "supplier_count": len(reservations),
                        "versions": [item.version_number for item in reservations],
                    },
                },
            )
            return batch_id, reservations

        return self._run(reserve, tender_id=tender_id)

    def _complete_export(self, reservation: ReservedTenderExport, published: PublishedFile, actor: str):
        def complete(service: StevenTenderService):
            version = service.repository.mark_version_ready(
                reservation.version_id,
                sha256=published.sha256,
                size_bytes=published.size_bytes,
                storage_key=published.storage_key,
                actor=actor,
                request_id=current_request_id(),
            )
            service.audit.append(
                actor=actor,
                action="tender.export",
                object_type="steven_tender_job",
                object_id=reservation.tender_id,
                before_after={
                    "before": {"version_status": "reserved"},
                    "after": {
                        "version_status": "ready",
                        "version_number": version.version_number,
                        "sha256": published.sha256,
                        "size_bytes": published.size_bytes,
                        "batch_id": reservation.export_batch_id,
                        "supplier_id": reservation.supplier_id,
                        "supplier_name_snapshot": reservation.supplier_name_snapshot,
                    },
                },
            )
            from app.modules.steven.tender_schemas import TenderExportView
            return TenderExportView(tender=service.get_tender(reservation.tender_id), version=service._version_view(version))
        return self._run(complete, tender_id=reservation.tender_id, version_id=reservation.version_id)

    def _fail_export(self, tender_id: str, version_id: str, actor: str, reason: str):
        def fail(service: StevenTenderService):
            version = service.repository.mark_version_failed(version_id, reason)
            service.audit.append(
                actor=actor,
                action="tender.export_failed",
                object_type="steven_tender_job",
                object_id=tender_id,
                before_after={"before": {"status": "reserved"}, "after": {"status": "failed", "version_number": version.version_number}},
            )
            return service._version_view(version)
        return self._run(fail, tender_id=tender_id, version_id=version_id)

    def _complete_batch_export(self, tender_id: str, batch_id: str, versions: list, actor: str):
        def complete(service: StevenTenderService):
            service.audit.append(
                actor=actor,
                action="tender.batch_export",
                object_type="steven_tender_job",
                object_id=tender_id,
                before_after={
                    "before": None,
                    "after": {
                        "batch_id": batch_id,
                        "versions": [
                            {
                                "version_number": item.version_number,
                                "status": item.status,
                                "supplier_id": item.supplier_id,
                            }
                            for item in versions
                        ],
                    },
                },
            )
            from app.modules.steven.tender_schemas import TenderBatchExportView
            return TenderBatchExportView(batch_id=batch_id, tender=service.get_tender(tender_id), versions=versions)

        return self._run(complete, tender_id=tender_id)

    def reconcile_export(self, tender_id: str, version_id: str, actor: str):
        version = self._run(
            lambda service: service.repository.get_version(version_id),
            tender_id=tender_id,
            version_id=version_id,
        )
        if version is None or version.tender_job_id != tender_id:
            raise ApiError(404, "version_not_found", "未找到导出版本。")
        if version.status != "reserved":
            raise ApiError(
                409,
                "version_not_reserved",
                "仅可对账 reserved 状态的正式 Word 版本。",
                {"status": version.status},
            )
        try:
            published = self._storage.inspect_existing(version.storage_key)
        except FileNotFoundError as error:
            self._fail_export(tender_id, version_id, actor, "published_file_missing_during_reconciliation")
            raise ApiError(
                409,
                "published_file_missing",
                "预留版本未找到已发布文件，已标记失败且版本号不复用。",
            ) from error
        except Exception as error:
            self._fail_export(
                tender_id,
                version_id,
                actor,
                f"published_file_invalid_during_reconciliation: {type(error).__name__}",
            )
            raise ApiError(
                409,
                "published_file_invalid",
                "预留版本文件无法通过可读性校验，已标记失败且版本号不复用。",
            ) from error

        suppliers = self._run(lambda service: service.repository.suppliers_for(tender_id), tender_id=tender_id)
        if version.supplier_id:
            suppliers = [item for item in suppliers if item.id == version.supplier_id]
            if not suppliers:
                raise ApiError(409, "version_supplier_missing", "批量导出版本关联的供应商已不可用。")
        reservation = ReservedTenderExport(
            tender_id=tender_id,
            version_id=version.id,
            version_number=version.version_number,
            filename=version.filename,
            storage_key=version.storage_key,
            job=self._run(lambda service: service._require_job(tender_id), tender_id=tender_id),
            suppliers=suppliers,
            rendered_body="",
            export_batch_id=version.export_batch_id,
            supplier_id=version.supplier_id,
            supplier_name_snapshot=version.supplier_name_snapshot,
        )
        return self._complete_export(reservation, published, actor)

    def list_versions(self, tender_id: str):
        return self._run(lambda service: service.list_versions(tender_id), tender_id=tender_id)

    def list_audit_events(self, tender_id: str):
        return self._run(lambda service: service.list_audit_events(tender_id), tender_id=tender_id)

    def print_summary(self, tender_id: str):
        return self._run(lambda service: service.print_summary(tender_id), tender_id=tender_id)

    def version_file(self, tender_id: str, version_number: int) -> Path:
        versions = self._run(lambda service: service.repository.versions_for(tender_id), tender_id=tender_id)
        version = next((item for item in versions if item.version_number == version_number and item.status == "ready"), None)
        if version is None:
            raise ApiError(404, "version_not_found", "未找到可下载的正式 Word 版本。")
        path = self._storage.resolve(version.storage_key)
        if not path.is_file():
            raise ApiError(404, "version_file_missing", "版本元数据存在，但文件不可用。")
        return path
