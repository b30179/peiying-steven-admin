from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy.exc import IntegrityError

from app.core.api_response import ApiError
from app.core.audit_context import current_request_id
from app.modules.platform.append_only_storage import LocalAppendOnlyFileStorage, PublishedFile
from app.modules.steven.inventory_excel import InventoryExcelRenderer
from app.modules.steven.inventory_import import InventoryImportParser
from app.modules.steven.inventory_service import StevenInventoryService


@dataclass(frozen=True)
class ReservedInventoryExport:
    count_id: str
    version_id: str
    version_number: int
    filename: str
    storage_key: str
    count: object
    lines: list


class StevenInventoryApplicationService:
    def __init__(
        self,
        unit_of_work,
        renderer: InventoryExcelRenderer,
        storage: LocalAppendOnlyFileStorage,
        parser: InventoryImportParser | None = None,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._renderer = renderer
        self._storage = storage
        self._parser = parser or InventoryImportParser()

    def _service(self, transaction) -> StevenInventoryService:
        return StevenInventoryService(transaction.repository, transaction.audit)

    def _run(
        self,
        callback,
        *,
        item_id: str | None = None,
        count_id: str | None = None,
        version_id: str | None = None,
        import_batch_id: str | None = None,
    ):
        try:
            with self._unit_of_work.begin(
                item_id=item_id,
                count_id=count_id,
                version_id=version_id,
                import_batch_id=import_batch_id,
            ) as transaction:
                return callback(self._service(transaction))
        except IntegrityError as error:
            diag = getattr(getattr(error, "orig", None), "diag", None)
            constraint = getattr(diag, "constraint_name", "") if diag else ""
            mappings = {
                "uq_steven_inventory_items_normalized_sku": (
                    "duplicate_sku",
                    "SKU 已存在。",
                ),
                "uq_steven_inventory_counts_number": (
                    "duplicate_count_number",
                    "盘点单编号已存在。",
                ),
                "uq_steven_inventory_count_item": (
                    "duplicate_count_item",
                    "同一盘点单不得重复同一 SKU。",
                ),
                "uq_steven_inventory_versions_count_version": (
                    "export_version_conflict",
                    "导出版本已被并发请求占用，请刷新后重试。",
                ),
                "uq_steven_inventory_versions_storage_key": (
                    "export_storage_conflict",
                    "导出文件路径已存在，拒绝覆盖历史版本。",
                ),
            }
            if constraint in mappings:
                code, message = mappings[constraint]
                raise ApiError(409, code, message) from error
            raise ApiError(409, "concurrent_write_conflict", "数据已被其他请求更新，请刷新后重试。") from error
        except ValueError as error:
            if str(error) == "duplicate_sku":
                raise ApiError(409, "duplicate_sku", "SKU 已存在。") from error
            if str(error) == "version_not_reserved":
                raise ApiError(409, "version_not_reserved", "导出版本状态已变化，请刷新后重试。") from error
            if str(error) in {"import_already_closed", "import_row_state_changed"}:
                raise ApiError(409, str(error), "导入状态已变化，请刷新后重试。") from error
            raise

    def list_items(self):
        return self._run(lambda service: service.list_items())

    def export_all_items(self, actor: str) -> tuple[str, bytes]:
        items = self.list_items()
        content = self._renderer.render_items(items=items)
        self._renderer.verify_items(content)
        self._run(lambda service: service.record_items_export(actor, len(items)))
        generated_at = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"steven-inventory-all-{generated_at}.xlsx", content

    def get_item(self, item_id: str):
        return self._run(lambda service: service.get_item(item_id), item_id=item_id)

    def create_item(self, payload, actor: str):
        return self._run(lambda service: service.create_item(payload, actor))

    def create_items(self, payloads, actor: str):
        return self._run(lambda service: service.create_items(payloads, actor))

    def update_item(self, item_id: str, payload, actor: str):
        return self._run(lambda service: service.update_item(item_id, payload, actor), item_id=item_id)

    def preflight_import(
        self,
        filename: str,
        content: bytes,
        actor: str,
        *,
        allow_existing_demo_updates: bool = False,
    ):
        return self._run(
            lambda service: service.preflight_import(
                filename,
                content,
                actor,
                self._parser,
                allow_existing_demo_updates=allow_existing_demo_updates,
            )
        )

    def get_import_batch(self, batch_id: str):
        return self._run(
            lambda service: service.get_import_batch(batch_id),
            import_batch_id=batch_id,
        )

    def confirm_import(self, batch_id: str, actor: str):
        return self._run(
            lambda service: service.confirm_import(batch_id, actor),
            import_batch_id=batch_id,
        )

    def list_counts(self):
        return self._run(lambda service: service.list_counts())

    def get_count(self, count_id: str):
        return self._run(lambda service: service.get_count(count_id), count_id=count_id)

    def create_count(self, payload, actor: str):
        return self._run(lambda service: service.create_count(payload, actor))

    def update_count(self, count_id: str, payload, actor: str):
        return self._run(lambda service: service.update_count(count_id, payload, actor), count_id=count_id)

    def submit(self, count_id: str, actor: str):
        return self._run(lambda service: service.submit(count_id, actor), count_id=count_id)

    def approve(self, count_id: str, actor: str, opinion: str):
        return self._run(lambda service: service.approve(count_id, actor, opinion), count_id=count_id)

    def return_for_revision(self, count_id: str, actor: str, opinion: str):
        return self._run(
            lambda service: service.return_for_revision(count_id, actor, opinion),
            count_id=count_id,
        )

    def export(self, count_id: str, actor: str):
        reservation = self._reserve_export(count_id, actor)
        try:
            published = self._storage.publish(
                object_id=count_id,
                version_number=reservation.version_number,
                filename=reservation.filename,
                render=lambda target: self._renderer.render_to(
                    target,
                    count=reservation.count,
                    lines=reservation.lines,
                    version_number=reservation.version_number,
                ),
            )
        except Exception as error:
            self._fail_export(count_id, reservation.version_id, actor, f"{type(error).__name__}: {error}")
            raise ApiError(
                500,
                "export_failed",
                "正式 Excel 导出失败，版本号已保留且不会复用。",
                {"version_number": reservation.version_number},
            ) from error
        return self._complete_export(reservation, published, actor)

    def _reserve_export(self, count_id: str, actor: str) -> ReservedInventoryExport:
        def reserve(service: StevenInventoryService):
            count = service._require_count(count_id)
            if count.status != "approved":
                raise ApiError(
                    409,
                    "formal_export_forbidden",
                    "仅已批准盘点单可生成正式 Excel。",
                    {"status": count.status},
                )
            lines = service.repository.lines_for(count_id)
            filename_template = (
                f"{date.today():%Y%m%d}_消耗品盘点_"
                f"{self._storage.safe_segment(count.count_number)}_v{{version}}.xlsx"
            )
            version = service.repository.reserve_version(
                count_id,
                actor,
                filename_template,
                self._storage.storage_template(count_id, filename_template),
            )
            service.audit.append(
                actor=actor,
                action="inventory.export_reserved",
                object_type="steven_inventory_count",
                object_id=count_id,
                before_after={
                    "before": None,
                    "after": {
                        "version_number": version.version_number,
                        "status": "reserved",
                    },
                },
            )
            return ReservedInventoryExport(
                count_id=count_id,
                version_id=version.id,
                version_number=version.version_number,
                filename=version.filename,
                storage_key=version.storage_key,
                count=count,
                lines=lines,
            )

        return self._run(reserve, count_id=count_id)

    def _complete_export(
        self,
        reservation: ReservedInventoryExport,
        published: PublishedFile,
        actor: str,
    ):
        def complete(service: StevenInventoryService):
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
                action="inventory.export",
                object_type="steven_inventory_count",
                object_id=reservation.count_id,
                before_after={
                    "before": {"version_status": "reserved"},
                    "after": {
                        "version_status": "ready",
                        "version_number": version.version_number,
                        "sha256": version.sha256,
                        "size_bytes": version.size_bytes,
                    },
                },
            )
            from app.modules.steven.inventory_schemas import InventoryExportView

            return InventoryExportView(
                count=service.get_count(reservation.count_id),
                version=service._version_view(version),
            )

        return self._run(
            complete,
            count_id=reservation.count_id,
            version_id=reservation.version_id,
        )

    def _fail_export(self, count_id: str, version_id: str, actor: str, reason: str):
        def fail(service: StevenInventoryService):
            version = service.repository.mark_version_failed(version_id, reason)
            service.audit.append(
                actor=actor,
                action="inventory.export_failed",
                object_type="steven_inventory_count",
                object_id=count_id,
                before_after={
                    "before": {"status": "reserved"},
                    "after": {
                        "status": "failed",
                        "version_number": version.version_number,
                    },
                },
            )

        return self._run(fail, count_id=count_id, version_id=version_id)

    def reconcile_export(self, count_id: str, version_id: str, actor: str):
        version = self._run(
            lambda service: service.repository.get_version(version_id),
            count_id=count_id,
            version_id=version_id,
        )
        if version is None or version.inventory_count_id != count_id:
            raise ApiError(404, "version_not_found", "未找到导出版本。")
        if version.status != "reserved":
            raise ApiError(
                409,
                "version_not_reserved",
                "仅可对账 reserved 状态的 Excel 版本。",
                {"status": version.status},
            )
        try:
            published = self._storage.inspect_existing(version.storage_key)
        except FileNotFoundError as error:
            self._fail_export(
                count_id,
                version_id,
                actor,
                "published_file_missing_during_reconciliation",
            )
            raise ApiError(
                409,
                "published_file_missing",
                "预留版本未找到已发布文件，已标记失败且版本号不复用。",
            ) from error
        except Exception as error:
            self._fail_export(
                count_id,
                version_id,
                actor,
                f"published_file_invalid_during_reconciliation: {type(error).__name__}",
            )
            raise ApiError(
                409,
                "published_file_invalid",
                "预留版本文件无法通过可读性校验，已标记失败且版本号不复用。",
            ) from error
        reservation = ReservedInventoryExport(
            count_id=count_id,
            version_id=version.id,
            version_number=version.version_number,
            filename=version.filename,
            storage_key=version.storage_key,
            count=self._run(lambda service: service._require_count(count_id), count_id=count_id),
            lines=self._run(
                lambda service: service.repository.lines_for(count_id),
                count_id=count_id,
            ),
        )
        return self._complete_export(reservation, published, actor)

    def list_versions(self, count_id: str):
        return self._run(lambda service: service.list_versions(count_id), count_id=count_id)

    def list_audit_events(self, count_id: str):
        return self._run(lambda service: service.list_audit_events(count_id), count_id=count_id)

    def version_file(self, count_id: str, version_number: int) -> Path:
        versions = self._run(
            lambda service: service.repository.versions_for(count_id),
            count_id=count_id,
        )
        version = next(
            (
                item
                for item in versions
                if item.version_number == version_number and item.status == "ready"
            ),
            None,
        )
        if version is None:
            raise ApiError(404, "version_not_found", "未找到可下载的正式 Excel 版本。")
        path = self._storage.resolve(version.storage_key)
        if not path.is_file():
            raise ApiError(404, "version_file_missing", "版本元数据存在，但文件不可用。")
        return path
