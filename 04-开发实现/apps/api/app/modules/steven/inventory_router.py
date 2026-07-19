from __future__ import annotations

import json
from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse

from app.core.api_response import success
from app.core.auth import Actor
from app.modules.steven.inventory_permissions import (
    require_inventory_approver,
    require_inventory_audit_reader,
    require_inventory_counter,
    require_inventory_exporter,
    require_inventory_reader,
    require_inventory_submitter,
    require_inventory_writer,
)
from app.modules.steven.inventory_schemas import (
    InventoryCountCreateRequest,
    InventoryCountUpdateRequest,
    InventoryDecisionRequest,
    InventoryItemCreateRequest,
    InventoryItemUpdateRequest,
    InventoryQuickEntryConfirmRequest,
    InventoryQuickEntryRequest,
)
from app.modules.steven.ai_assist_service import InventorySmartMapping
from app.modules.steven.inventory_smart_import import build_standard_inventory_workbook, inspect_inventory_workbook

inventory_router = APIRouter(prefix="/api/v1/steven", tags=["steven-inventory"])


def inventory_application(request: Request):
    return request.app.state.inventory_application


def ai_assist_service(request: Request):
    return request.app.state.ai_assist_service


@inventory_router.get("/inventory-items")
async def list_inventory_items(
    request: Request,
    _: Actor = Depends(require_inventory_reader),
) -> dict:
    records = [
        item.model_dump(mode="json")
        for item in inventory_application(request).list_items()
    ]
    return success(
        request,
        records,
        {"page": 1, "page_size": len(records), "total": len(records)},
    )


@inventory_router.get("/inventory-items/export")
async def export_all_inventory_items(
    request: Request,
    actor: Actor = Depends(require_inventory_exporter),
) -> StreamingResponse:
    filename, content = inventory_application(request).export_all_items(actor.actor_id)
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@inventory_router.post("/inventory-items", status_code=status.HTTP_201_CREATED)
async def create_inventory_item(
    request: Request,
    payload: InventoryItemCreateRequest,
    actor: Actor = Depends(require_inventory_writer),
) -> dict:
    result = inventory_application(request).create_item(payload, actor.actor_id)
    return success(request, result.model_dump(mode="json"))


@inventory_router.post("/inventory-items/import/preflight")
async def preflight_inventory_import(
    request: Request,
    file: Annotated[UploadFile, File()],
    actor: Actor = Depends(require_inventory_writer),
) -> dict:
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        from app.core.api_response import ApiError

        raise ApiError(413, "file_too_large", "导入文件不得超过 5 MB。")
    result = inventory_application(request).preflight_import(
        file.filename or "inventory.xlsx",
        content,
        actor.actor_id,
    )
    return success(request, result.model_dump(mode="json"))


@inventory_router.post("/inventory-items/import/smart")
async def smart_inventory_import(
    request: Request,
    file: Annotated[UploadFile, File()],
    mapping_json: Annotated[str | None, Form()] = None,
    actor: Actor = Depends(require_inventory_writer),
) -> dict:
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        from app.core.api_response import ApiError

        raise ApiError(413, "file_too_large", "导入文件不得超过 5 MB。")
    headers, samples = inspect_inventory_workbook(file.filename or "inventory.xlsx", content)
    if mapping_json is None:
        mapping = ai_assist_service(request).smart_inventory_mapping(headers, samples)
        return success(request, {**mapping.model_dump(mode="json"), "headers": headers, "sample_rows": samples})
    try:
        raw_mapping = json.loads(mapping_json)
        mapping = InventorySmartMapping.model_validate({"mapping": raw_mapping, "unmapped_columns": []})
    except Exception as error:
        from app.core.api_response import ApiError

        raise ApiError(422, "invalid_mapping", "列映射格式无效。") from error
    normalized_content = build_standard_inventory_workbook(content, mapping.mapping)
    batch = inventory_application(request).preflight_import(
        f"smart-{file.filename or 'inventory.xlsx'}",
        normalized_content,
        actor.actor_id,
        allow_existing_demo_updates=True,
    )
    return success(request, {
        **mapping.model_dump(mode="json"),
        "headers": headers,
        "sample_rows": samples,
        "batch": batch.model_dump(mode="json"),
    })


@inventory_router.post("/inventory-items/quick-entry")
async def quick_entry_inventory_items(
    request: Request,
    payload: InventoryQuickEntryRequest,
    _: Actor = Depends(require_inventory_writer),
) -> dict:
    result = ai_assist_service(request).quick_inventory_entry(payload.text)
    return success(request, result.model_dump(mode="json"))


@inventory_router.post("/inventory-items/quick-entry/confirm", status_code=status.HTTP_201_CREATED)
async def confirm_quick_entry_inventory_items(
    request: Request,
    payload: InventoryQuickEntryConfirmRequest,
    actor: Actor = Depends(require_inventory_writer),
) -> dict:
    records = inventory_application(request).create_items(payload.items, actor.actor_id)
    return success(request, [record.model_dump(mode="json") for record in records])


@inventory_router.get("/inventory-items/import/{batch_id}")
async def get_inventory_import(
    request: Request,
    batch_id: str,
    _: Actor = Depends(require_inventory_writer),
) -> dict:
    result = inventory_application(request).get_import_batch(batch_id)
    return success(request, result.model_dump(mode="json"))


@inventory_router.post("/inventory-items/import/{batch_id}/confirm")
async def confirm_inventory_import(
    request: Request,
    batch_id: str,
    actor: Actor = Depends(require_inventory_writer),
) -> dict:
    result = inventory_application(request).confirm_import(batch_id, actor.actor_id)
    return success(request, result.model_dump(mode="json"))


@inventory_router.get("/inventory-items/{item_id}")
async def get_inventory_item(
    request: Request,
    item_id: str,
    _: Actor = Depends(require_inventory_reader),
) -> dict:
    result = inventory_application(request).get_item(item_id)
    return success(request, result.model_dump(mode="json"))


@inventory_router.patch("/inventory-items/{item_id}")
async def update_inventory_item(
    request: Request,
    item_id: str,
    payload: InventoryItemUpdateRequest,
    actor: Actor = Depends(require_inventory_writer),
) -> dict:
    result = inventory_application(request).update_item(item_id, payload, actor.actor_id)
    return success(request, result.model_dump(mode="json"))


@inventory_router.get("/inventory-counts")
async def list_inventory_counts(
    request: Request,
    _: Actor = Depends(require_inventory_reader),
) -> dict:
    records = [
        item.model_dump(mode="json")
        for item in inventory_application(request).list_counts()
    ]
    return success(
        request,
        records,
        {"page": 1, "page_size": len(records), "total": len(records)},
    )


@inventory_router.post("/inventory-counts", status_code=status.HTTP_201_CREATED)
async def create_inventory_count(
    request: Request,
    payload: InventoryCountCreateRequest,
    actor: Actor = Depends(require_inventory_counter),
) -> dict:
    result = inventory_application(request).create_count(payload, actor.actor_id)
    return success(request, result.model_dump(mode="json"))


@inventory_router.get("/inventory-counts/{count_id}")
async def get_inventory_count(
    request: Request,
    count_id: str,
    _: Actor = Depends(require_inventory_reader),
) -> dict:
    result = inventory_application(request).get_count(count_id)
    return success(request, result.model_dump(mode="json"))


@inventory_router.patch("/inventory-counts/{count_id}")
async def update_inventory_count(
    request: Request,
    count_id: str,
    payload: InventoryCountUpdateRequest,
    actor: Actor = Depends(require_inventory_counter),
) -> dict:
    result = inventory_application(request).update_count(count_id, payload, actor.actor_id)
    return success(request, result.model_dump(mode="json"))


@inventory_router.post("/inventory-counts/{count_id}/submit")
async def submit_inventory_count(
    request: Request,
    count_id: str,
    actor: Actor = Depends(require_inventory_submitter),
) -> dict:
    result = inventory_application(request).submit(count_id, actor.actor_id)
    return success(request, result.model_dump(mode="json"))


@inventory_router.post("/inventory-counts/{count_id}/approve")
async def approve_inventory_count(
    request: Request,
    count_id: str,
    payload: InventoryDecisionRequest,
    actor: Actor = Depends(require_inventory_approver),
) -> dict:
    result = inventory_application(request).approve(count_id, actor.actor_id, payload.opinion)
    return success(request, result.model_dump(mode="json"))


@inventory_router.post("/inventory-counts/{count_id}/return")
async def return_inventory_count(
    request: Request,
    count_id: str,
    payload: InventoryDecisionRequest,
    actor: Actor = Depends(require_inventory_approver),
) -> dict:
    result = inventory_application(request).return_for_revision(
        count_id,
        actor.actor_id,
        payload.opinion,
    )
    return success(request, result.model_dump(mode="json"))


@inventory_router.post("/inventory-counts/{count_id}/export")
async def export_inventory_count(
    request: Request,
    count_id: str,
    actor: Actor = Depends(require_inventory_exporter),
) -> dict:
    result = inventory_application(request).export(count_id, actor.actor_id)
    return success(request, result.model_dump(mode="json"))


@inventory_router.get("/inventory-counts/{count_id}/versions")
async def list_inventory_versions(
    request: Request,
    count_id: str,
    _: Actor = Depends(require_inventory_reader),
) -> dict:
    records = [
        item.model_dump(mode="json")
        for item in inventory_application(request).list_versions(count_id)
    ]
    return success(
        request,
        records,
        {"page": 1, "page_size": len(records), "total": len(records)},
    )


@inventory_router.post("/inventory-counts/{count_id}/versions/{version_id}/reconcile")
async def reconcile_inventory_version(
    request: Request,
    count_id: str,
    version_id: str,
    actor: Actor = Depends(require_inventory_exporter),
) -> dict:
    result = inventory_application(request).reconcile_export(
        count_id,
        version_id,
        actor.actor_id,
    )
    return success(request, result.model_dump(mode="json"))


@inventory_router.get("/inventory-counts/{count_id}/versions/{version_number}/download")
async def download_inventory_version(
    request: Request,
    count_id: str,
    version_number: int,
    _: Actor = Depends(require_inventory_exporter),
) -> FileResponse:
    path = inventory_application(request).version_file(count_id, version_number)
    return FileResponse(
        path=path,
        filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@inventory_router.get("/inventory-counts/{count_id}/audit-events")
async def list_inventory_audit_events(
    request: Request,
    count_id: str,
    _: Actor = Depends(require_inventory_audit_reader),
) -> dict:
    records = inventory_application(request).list_audit_events(count_id)
    return success(
        request,
        records,
        {"page": 1, "page_size": len(records), "total": len(records)},
    )
