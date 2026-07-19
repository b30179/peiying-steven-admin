from __future__ import annotations

import unicodedata

from app.core.api_response import ApiError
from app.core.audit_context import current_request_id
from app.modules.steven.inventory_repository import utc_now
from app.modules.steven.inventory_schemas import (
    InventoryCountCreateRequest,
    InventoryCountLineView,
    InventoryCountUpdateRequest,
    InventoryCountView,
    InventoryImportBatchView,
    InventoryImportRowView,
    InventoryItemCreateRequest,
    InventoryItemUpdateRequest,
    InventoryItemView,
    InventoryVersionView,
)


OCR_PURPOSE = "inventory_sheet_extraction"
AI_PURPOSE = "inventory_exception_explanation"


def normalize_sku(value: str) -> tuple[str, str]:
    display = " ".join(unicodedata.normalize("NFKC", value).split())
    return display, display.casefold()


class StevenInventoryService:
    def __init__(self, repository, audit) -> None:
        self.repository = repository
        self.audit = audit

    def list_items(self) -> list[InventoryItemView]:
        return [self._item_view(item) for item in self.repository.list_items()]

    def record_items_export(self, actor: str, item_count: int) -> None:
        self.audit.append(
            actor=actor,
            action="inventory.items.export_all",
            object_type="steven_inventory_item_collection",
            object_id="all",
            before_after={"before": None, "after": {"item_count": item_count}},
        )

    def get_item(self, item_id: str) -> InventoryItemView:
        return self._item_view(self._require_item(item_id))

    def create_item(self, payload: InventoryItemCreateRequest, actor: str) -> InventoryItemView:
        sku, normalized_sku = normalize_sku(payload.sku)
        if not normalized_sku:
            raise ApiError(422, "sku_required", "SKU 必填。")
        self._validate_stock(payload.book_quantity, payload.safety_stock, payload.target_stock)
        try:
            item = self.repository.create_item(
                sku=sku,
                normalized_sku=normalized_sku,
                item_name=payload.item_name,
                category=payload.category,
                location=payload.location,
                book_quantity=payload.book_quantity,
                safety_stock=payload.safety_stock,
                target_stock=payload.target_stock,
                is_demo=payload.is_demo,
                created_by=actor,
                updated_by=actor,
            )
        except ValueError as error:
            self._raise_value_error(error)
        self.audit.append(
            actor=actor,
            action="inventory.item.create",
            object_type="steven_inventory_item",
            object_id=item.id,
            before_after={"before": None, "after": {"sku": item.sku, "is_demo": item.is_demo}},
        )
        return self._item_view(item)

    def create_items(self, payloads: list[InventoryItemCreateRequest], actor: str) -> list[InventoryItemView]:
        return [self.create_item(payload, actor) for payload in payloads]

    def update_item(self, item_id: str, payload: InventoryItemUpdateRequest, actor: str) -> InventoryItemView:
        item = self._require_item(item_id)
        before = {"sku": item.sku, "book_quantity": item.book_quantity, "status": item.status}
        values = payload.model_dump(exclude_unset=True)
        if "sku" in values and values["sku"] is not None:
            item.sku, item.normalized_sku = normalize_sku(values.pop("sku"))
            if not item.normalized_sku:
                raise ApiError(422, "sku_required", "SKU 必填。")
        for key, value in values.items():
            if value is not None:
                setattr(item, key, value)
        self._validate_stock(item.book_quantity, item.safety_stock, item.target_stock)
        try:
            self.repository.save_item(item, actor)
        except ValueError as error:
            self._raise_value_error(error)
        self.audit.append(
            actor=actor,
            action="inventory.item.update",
            object_type="steven_inventory_item",
            object_id=item.id,
            before_after={
                "before": before,
                "after": {"sku": item.sku, "book_quantity": item.book_quantity, "status": item.status},
            },
        )
        return self._item_view(item)

    def list_counts(self) -> list[InventoryCountView]:
        return [self._count_view(item) for item in self.repository.list_counts()]

    def preflight_import(
        self,
        filename: str,
        content: bytes,
        actor: str,
        parser,
        *,
        allow_existing_demo_updates: bool = False,
    ) -> InventoryImportBatchView:
        existing_items = self.repository.list_items()
        existing = {item.normalized_sku for item in existing_items}
        updatable = {
            item.normalized_sku
            for item in existing_items
            if allow_existing_demo_updates and item.is_demo
        }
        parsed = parser.parse(
            filename,
            content,
            existing,
            updatable_normalized_skus=updatable,
        )
        batch = self.repository.create_import_batch(
            original_filename=parsed.original_filename,
            content_sha256=parsed.content_sha256,
            rows=parsed.rows,
            issues=parsed.issues,
            actor=actor,
            request_id=current_request_id() or "unscoped",
        )
        self.audit.append(
            actor=actor,
            action="inventory.import.preflight",
            object_type="steven_inventory_import_batch",
            object_id=batch.id,
            before_after={
                "before": None,
                "after": {
                    "row_count": batch.row_count,
                    "valid_count": batch.valid_count,
                    "invalid_count": batch.invalid_count,
                    "issue_count": len(batch.issues),
                    "allow_existing_demo_updates": allow_existing_demo_updates,
                },
            },
        )
        return self._import_batch_view(batch)

    def get_import_batch(self, batch_id: str) -> InventoryImportBatchView:
        return self._import_batch_view(self._require_import_batch(batch_id))

    def confirm_import(self, batch_id: str, actor: str) -> InventoryImportBatchView:
        batch = self._require_import_batch(batch_id)
        if batch.status != "preflight_ready":
            raise ApiError(
                409,
                "import_already_closed",
                "该导入批次已完成或已关闭。",
                {"status": batch.status},
            )
        if batch.invalid_count or batch.issues:
            raise ApiError(
                409,
                "import_preflight_blocked",
                "预检仍有阻断错误，请修正 Excel 后重新上传。",
                {
                    "invalid_count": batch.invalid_count,
                    "issue_count": len(batch.issues),
                },
            )
        rows = self.repository.import_rows_for(batch.id)
        if not rows:
            raise ApiError(409, "import_empty", "导入批次没有可确认的数据行。")
        imported_item_ids: dict[int, str] = {}
        created_item_ids: list[str] = []
        updated_item_ids: list[str] = []
        for row in rows:
            if row.status != "valid":
                raise ApiError(409, "import_row_state_changed", "导入行状态已变化，请重新预检。")
            values = row.values
            action = values.get("_import_action", "create")
            if action == "update":
                item = self.repository.get_item_by_normalized_sku(row.normalized_sku, for_update=True)
                if item is None:
                    raise ApiError(409, "import_update_target_missing", "待更新的库存品项已不存在，请重新预检。")
                if not item.is_demo:
                    raise ApiError(403, "import_update_non_demo_forbidden", "智能导入只允许更新脱敏 Demo 库存品项。")
                item.sku = values["sku"]
                item.normalized_sku = row.normalized_sku
                item.item_name = values["item_name"]
                item.category = values["category"]
                item.location = values["location"]
                item.book_quantity = values["book_quantity"]
                item.safety_stock = values["safety_stock"]
                item.target_stock = values["target_stock"]
                self.repository.save_item(item, actor)
                updated_item_ids.append(item.id)
            elif action == "create":
                item = self.repository.create_item(
                    sku=values["sku"],
                    normalized_sku=row.normalized_sku,
                    item_name=values["item_name"],
                    category=values["category"],
                    location=values["location"],
                    book_quantity=values["book_quantity"],
                    safety_stock=values["safety_stock"],
                    target_stock=values["target_stock"],
                    is_demo=True,
                    created_by=actor,
                    updated_by=actor,
                )
                created_item_ids.append(item.id)
            else:
                raise ApiError(409, "invalid_import_action", "导入动作无效，请重新预检。")
            imported_item_ids[row.row_number] = item.id
        self.repository.confirm_import_batch(batch, imported_item_ids, actor)
        self.audit.append(
            actor=actor,
            action="inventory.import.confirm",
            object_type="steven_inventory_import_batch",
            object_id=batch.id,
            before_after={
                "before": {"status": "preflight_ready"},
                "after": {
                    "status": "confirmed",
                    "imported_count": len(imported_item_ids),
                    "imported_item_ids": list(imported_item_ids.values()),
                    "created_count": len(created_item_ids),
                    "created_item_ids": created_item_ids,
                    "updated_count": len(updated_item_ids),
                    "updated_item_ids": updated_item_ids,
                },
            },
        )
        return self._import_batch_view(self._require_import_batch(batch.id))

    def get_count(self, count_id: str) -> InventoryCountView:
        return self._count_view(self._require_count(count_id))

    def create_count(self, payload: InventoryCountCreateRequest, actor: str) -> InventoryCountView:
        lines = self._prepare_lines(payload.lines)
        try:
            count = self.repository.create_count(
                count_number=payload.count_number,
                count_date=payload.count_date,
                is_demo=payload.is_demo,
                created_by=actor,
                updated_by=actor,
            )
            self.repository.replace_lines(count.id, lines, actor)
        except ValueError as error:
            self._raise_value_error(error)
        self.audit.append(
            actor=actor,
            action="inventory.count.create",
            object_type="steven_inventory_count",
            object_id=count.id,
            before_after={
                "before": None,
                "after": {"count_number": count.count_number, "status": count.status, "line_count": len(lines)},
            },
        )
        return self._count_view(count)

    def update_count(self, count_id: str, payload: InventoryCountUpdateRequest, actor: str) -> InventoryCountView:
        count = self._require_count(count_id)
        if count.status not in {"draft", "returned"}:
            raise ApiError(409, "inventory_count_not_editable", "当前盘点状态不可修订。", {"status": count.status})
        before = {"status": count.status, "updated_at": count.updated_at.isoformat()}
        if payload.count_date is not None:
            count.count_date = payload.count_date
        if payload.lines is not None:
            self.repository.replace_lines(count.id, self._prepare_lines(payload.lines), actor)
        count.status = "draft"
        count.submitted_by = None
        count.submitted_at = None
        count.decided_by = None
        count.decided_at = None
        count.decision_opinion = None
        self.repository.save_count(count, actor)
        self.audit.append(
            actor=actor,
            action="inventory.count.update",
            object_type="steven_inventory_count",
            object_id=count.id,
            before_after={"before": before, "after": {"status": count.status, "approval_reset": True}},
        )
        return self._count_view(count)

    def submit(self, count_id: str, actor: str) -> InventoryCountView:
        count = self._require_count(count_id)
        if count.status not in {"draft", "returned"}:
            raise ApiError(409, "inventory_count_not_submittable", "当前盘点状态不可提交。", {"status": count.status})
        lines = self.repository.lines_for(count.id)
        if not lines:
            raise ApiError(422, "inventory_count_lines_required", "盘点单至少需要一条明细。")
        self._validate_prepared_lines(lines)
        before = {"status": count.status}
        count.status = "submitted"
        count.submitted_by = actor
        count.submitted_at = utc_now()
        count.decided_by = None
        count.decided_at = None
        count.decision_opinion = None
        self.repository.save_count(count, actor)
        self.audit.append(
            actor=actor,
            action="inventory.count.submit",
            object_type="steven_inventory_count",
            object_id=count.id,
            before_after={"before": before, "after": {"status": count.status, "submitted_by": actor}},
        )
        return self._count_view(count)

    def approve(self, count_id: str, actor: str, opinion: str) -> InventoryCountView:
        return self._decide(count_id, actor, "approved", opinion)

    def return_for_revision(self, count_id: str, actor: str, opinion: str) -> InventoryCountView:
        if not opinion.strip():
            raise ApiError(422, "return_opinion_required", "退回必须填写意见。")
        return self._decide(count_id, actor, "returned", opinion)

    def _decide(self, count_id: str, actor: str, target: str, opinion: str) -> InventoryCountView:
        count = self._require_count(count_id)
        if count.status != "submitted":
            raise ApiError(409, "approval_closed", "该盘点单不在待审批状态。", {"status": count.status})
        if count.submitted_by == actor:
            raise ApiError(403, "self_approval_forbidden", "提交人不得审批自己的盘点单。")
        before = {"status": count.status, "submitted_by": count.submitted_by}
        count.status = target
        count.decided_by = actor
        count.decided_at = utc_now()
        count.decision_opinion = opinion.strip()
        self.repository.save_count(count, actor)
        self.audit.append(
            actor=actor,
            action="inventory.count.approve" if target == "approved" else "inventory.count.return",
            object_type="steven_inventory_count",
            object_id=count.id,
            before_after={
                "before": before,
                "after": {"status": target, "decided_by": actor, "opinion": count.decision_opinion},
            },
        )
        return self._count_view(count)

    def list_versions(self, count_id: str) -> list[InventoryVersionView]:
        self._require_count(count_id)
        return [self._version_view(item) for item in self.repository.versions_for(count_id)]

    def list_audit_events(self, count_id: str) -> list[dict]:
        self._require_count(count_id)
        return self.audit.list_for_object(count_id)

    def _prepare_lines(self, inputs) -> list[dict]:
        prepared: list[dict] = []
        seen: set[str] = set()
        for value in inputs:
            if value.inventory_item_id in seen:
                raise ApiError(409, "duplicate_count_item", "同一盘点单不得重复同一 SKU。")
            seen.add(value.inventory_item_id)
            item = self._require_item(value.inventory_item_id)
            if item.status != "active":
                raise ApiError(409, "inventory_item_inactive", "停用品项不可加入新盘点。", {"sku": item.sku})
            suggested = max(0, item.target_stock - value.counted_quantity)
            confirmed = value.confirmed_order_quantity
            if confirmed is None:
                confirmed = suggested
            reason = (value.manual_reason or "").strip() or None
            if confirmed != suggested and not reason:
                raise ApiError(
                    422,
                    "manual_reason_required",
                    "人工确认补货量偏离系统建议时必须填写理由。",
                    {"sku": item.sku, "suggested_order_quantity": suggested},
                )
            prepared.append(
                {
                    "inventory_item_id": item.id,
                    "sku_snapshot": item.sku,
                    "item_name_snapshot": item.item_name,
                    "location_snapshot": item.location,
                    "book_quantity_snapshot": item.book_quantity,
                    "safety_stock_snapshot": item.safety_stock,
                    "target_stock_snapshot": item.target_stock,
                    "counted_quantity": value.counted_quantity,
                    "difference_quantity": value.counted_quantity - item.book_quantity,
                    "is_low_stock": value.counted_quantity < item.safety_stock,
                    "suggested_order_quantity": suggested,
                    "confirmed_order_quantity": confirmed,
                    "manual_reason": reason,
                    "remark": (value.remark or "").strip() or None,
                }
            )
        return prepared

    @staticmethod
    def _validate_prepared_lines(lines) -> None:
        for line in lines:
            if line.confirmed_order_quantity != line.suggested_order_quantity and not (line.manual_reason or "").strip():
                raise ApiError(422, "manual_reason_required", "人工确认补货量偏离系统建议时必须填写理由。")

    @staticmethod
    def _validate_stock(book_quantity: int, safety_stock: int, target_stock: int) -> None:
        if min(book_quantity, safety_stock, target_stock) < 0:
            raise ApiError(422, "inventory_quantity_negative", "库存数量必须为非负整数。")
        if target_stock < safety_stock:
            raise ApiError(422, "target_below_safety_stock", "目标库存不得低于安全库存。")

    def _require_item(self, item_id: str):
        item = self.repository.get_item(item_id)
        if item is None:
            raise ApiError(404, "inventory_item_not_found", "未找到库存品项。")
        return item

    def _require_count(self, count_id: str):
        count = self.repository.get_count(count_id)
        if count is None:
            raise ApiError(404, "inventory_count_not_found", "未找到盘点单。")
        return count

    def _require_import_batch(self, batch_id: str):
        batch = self.repository.get_import_batch(batch_id)
        if batch is None:
            raise ApiError(404, "inventory_import_not_found", "未找到库存导入批次。")
        return batch

    @staticmethod
    def _item_view(item) -> InventoryItemView:
        return InventoryItemView(
            id=item.id,
            sku=item.sku,
            item_name=item.item_name,
            category=item.category,
            location=item.location,
            book_quantity=item.book_quantity,
            safety_stock=item.safety_stock,
            target_stock=item.target_stock,
            status=item.status,
            is_demo=item.is_demo,
            created_by=item.created_by,
            updated_by=item.updated_by,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    def _count_view(self, count) -> InventoryCountView:
        return InventoryCountView(
            id=count.id,
            count_number=count.count_number,
            count_date=count.count_date,
            status=count.status,
            submitted_by=count.submitted_by,
            submitted_at=count.submitted_at,
            decided_by=count.decided_by,
            decided_at=count.decided_at,
            decision_opinion=count.decision_opinion,
            is_demo=count.is_demo,
            lines=[self._line_view(item) for item in self.repository.lines_for(count.id)],
            versions=[self._version_view(item) for item in self.repository.versions_for(count.id)],
            created_by=count.created_by,
            updated_by=count.updated_by,
            created_at=count.created_at,
            updated_at=count.updated_at,
        )

    @staticmethod
    def _line_view(item) -> InventoryCountLineView:
        return InventoryCountLineView(
            id=item.id,
            inventory_item_id=item.inventory_item_id,
            sku=item.sku_snapshot,
            item_name=item.item_name_snapshot,
            location=item.location_snapshot,
            book_quantity_snapshot=item.book_quantity_snapshot,
            safety_stock_snapshot=item.safety_stock_snapshot,
            target_stock_snapshot=item.target_stock_snapshot,
            counted_quantity=item.counted_quantity,
            difference_quantity=item.difference_quantity,
            is_low_stock=item.is_low_stock,
            suggested_order_quantity=item.suggested_order_quantity,
            confirmed_order_quantity=item.confirmed_order_quantity,
            manual_reason=item.manual_reason,
            remark=item.remark,
        )

    @staticmethod
    def _version_view(item) -> InventoryVersionView:
        return InventoryVersionView(
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
        )

    def _import_batch_view(self, batch) -> InventoryImportBatchView:
        return InventoryImportBatchView(
            id=batch.id,
            original_filename=batch.original_filename,
            content_sha256=batch.content_sha256,
            status=batch.status,
            row_count=batch.row_count,
            valid_count=batch.valid_count,
            invalid_count=batch.invalid_count,
            issues=batch.issues,
            rows=[
                InventoryImportRowView(
                    id=row.id,
                    row_number=row.row_number,
                    raw_values=row.raw_values,
                    values=row.values,
                    normalized_sku=row.normalized_sku,
                    status=row.status,
                    errors=row.errors,
                    imported_item_id=row.imported_item_id,
                )
                for row in self.repository.import_rows_for(batch.id)
            ],
            created_by=batch.created_by,
            confirmed_by=batch.confirmed_by,
            request_id=batch.request_id,
            created_at=batch.created_at,
            confirmed_at=batch.confirmed_at,
        )

    @staticmethod
    def _raise_value_error(error: ValueError) -> None:
        code = str(error)
        messages = {
            "duplicate_sku": "SKU 已存在。",
            "duplicate_count_number": "盘点单编号已存在。",
            "duplicate_count_item": "同一盘点单不得重复同一 SKU。",
        }
        if code in messages:
            raise ApiError(409, code, messages[code]) from error
        raise error
