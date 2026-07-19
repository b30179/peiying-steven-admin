from __future__ import annotations

import os
from pathlib import Path
import sys

from sqlalchemy.engine import make_url


PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = PROJECT_ROOT / "apps" / "api"
EXPECTED_DATABASE = "puiying_steven_demo"

sys.path.insert(0, str(API_ROOT))

from app.core.config import Settings  # noqa: E402
from app.main import LazyPostgresInventoryApplication, create_app  # noqa: E402
from app.modules.steven.inventory_schemas import InventoryItemCreateRequest  # noqa: E402
from app.modules.steven.inventory_service import normalize_sku  # noqa: E402


DEMO_ITEMS = (
    {
        "sku": "DEMO-S3-PAPER-A4",
        "item_name": "A4 影印纸（脱敏）",
        "category": "办公耗材",
        "location": "DEMO-STORE-A",
        "book_quantity": 12,
        "safety_stock": 10,
        "target_stock": 30,
        "is_demo": True,
    },
    {
        "sku": "DEMO-S3-PEN-BLUE",
        "item_name": "蓝色原子笔（脱敏）",
        "category": "书写用品",
        "location": "DEMO-STORE-B",
        "book_quantity": 20,
        "safety_stock": 5,
        "target_stock": 20,
        "is_demo": True,
    },
    {
        "sku": "DEMO-S3-MARKER-WHITEBOARD",
        "item_name": "白板笔（脱敏）",
        "category": "教学耗材",
        "location": "DEMO-STORE-A",
        "book_quantity": 15,
        "safety_stock": 8,
        "target_stock": 25,
        "is_demo": True,
    },
    {
        "sku": "DEMO-S3-FOLDER-A4",
        "item_name": "A4 文件夹（脱敏）",
        "category": "文件用品",
        "location": "DEMO-STORE-B",
        "book_quantity": 18,
        "safety_stock": 6,
        "target_stock": 18,
        "is_demo": True,
    },
    {
        "sku": "DEMO-S3-STAPLES-246",
        "item_name": "订书钉 24/6（脱敏）",
        "category": "装订耗材",
        "location": "DEMO-STORE-A",
        "book_quantity": 30,
        "safety_stock": 12,
        "target_stock": 40,
        "is_demo": True,
    },
    {
        "sku": "DEMO-S3-NOTE-A5",
        "item_name": "A5 便笺本（脱敏）",
        "category": "纸品",
        "location": "DEMO-STORE-C",
        "book_quantity": 9,
        "safety_stock": 12,
        "target_stock": 28,
        "is_demo": True,
    },
    {
        "sku": "DEMO-S3-ENVELOPE-C5",
        "item_name": "C5 信封（脱敏）",
        "category": "纸品",
        "location": "DEMO-STORE-C",
        "book_quantity": 24,
        "safety_stock": 10,
        "target_stock": 30,
        "is_demo": True,
    },
    {
        "sku": "DEMO-S3-TAPE-CLEAR",
        "item_name": "透明胶带（脱敏）",
        "category": "黏贴用品",
        "location": "DEMO-STORE-A",
        "book_quantity": 7,
        "safety_stock": 6,
        "target_stock": 18,
        "is_demo": True,
    },
    {
        "sku": "DEMO-S3-GLUE-STICK",
        "item_name": "固体胶（脱敏）",
        "category": "黏贴用品",
        "location": "DEMO-STORE-A",
        "book_quantity": 5,
        "safety_stock": 8,
        "target_stock": 20,
        "is_demo": True,
    },
    {
        "sku": "DEMO-S3-CLIP-SMALL",
        "item_name": "小号长尾夹（脱敏）",
        "category": "装订耗材",
        "location": "DEMO-STORE-B",
        "book_quantity": 40,
        "safety_stock": 15,
        "target_stock": 40,
        "is_demo": True,
    },
    {
        "sku": "DEMO-S3-CLIP-LARGE",
        "item_name": "大号长尾夹（脱敏）",
        "category": "装订耗材",
        "location": "DEMO-STORE-B",
        "book_quantity": 11,
        "safety_stock": 10,
        "target_stock": 25,
        "is_demo": True,
    },
    {
        "sku": "DEMO-S3-ERASER-WHITE",
        "item_name": "白色橡皮擦（脱敏）",
        "category": "书写用品",
        "location": "DEMO-STORE-B",
        "book_quantity": 14,
        "safety_stock": 6,
        "target_stock": 18,
        "is_demo": True,
    },
    {
        "sku": "DEMO-S3-PENCIL-HB",
        "item_name": "HB 铅笔（脱敏）",
        "category": "书写用品",
        "location": "DEMO-STORE-B",
        "book_quantity": 32,
        "safety_stock": 12,
        "target_stock": 36,
        "is_demo": True,
    },
    {
        "sku": "DEMO-S3-HIGHLIGHTER-YELLOW",
        "item_name": "黄色荧光笔（脱敏）",
        "category": "书写用品",
        "location": "DEMO-STORE-B",
        "book_quantity": 6,
        "safety_stock": 8,
        "target_stock": 20,
        "is_demo": True,
    },
    {
        "sku": "DEMO-S3-LABEL-RECT",
        "item_name": "长方形标签贴（脱敏）",
        "category": "标签用品",
        "location": "DEMO-STORE-C",
        "book_quantity": 18,
        "safety_stock": 8,
        "target_stock": 24,
        "is_demo": True,
    },
    {
        "sku": "DEMO-S3-BATTERY-AA",
        "item_name": "AA 电池（脱敏）",
        "category": "通用耗材",
        "location": "DEMO-STORE-C",
        "book_quantity": 10,
        "safety_stock": 10,
        "target_stock": 24,
        "is_demo": True,
    },
    {
        "sku": "DEMO-S3-BATTERY-AAA",
        "item_name": "AAA 电池（脱敏）",
        "category": "通用耗材",
        "location": "DEMO-STORE-C",
        "book_quantity": 4,
        "safety_stock": 8,
        "target_stock": 20,
        "is_demo": True,
    },
    {
        "sku": "DEMO-S3-TISSUE-BOX",
        "item_name": "盒装纸巾（脱敏）",
        "category": "清洁耗材",
        "location": "DEMO-STORE-A",
        "book_quantity": 16,
        "safety_stock": 10,
        "target_stock": 24,
        "is_demo": True,
    },
    {
        "sku": "DEMO-S3-WIPE-CLOTH",
        "item_name": "清洁抹布（脱敏）",
        "category": "清洁耗材",
        "location": "DEMO-STORE-A",
        "book_quantity": 8,
        "safety_stock": 5,
        "target_stock": 12,
        "is_demo": True,
    },
    {
        "sku": "DEMO-S3-GLOVE-DISPOSABLE",
        "item_name": "一次性手套（脱敏）",
        "category": "清洁耗材",
        "location": "DEMO-STORE-C",
        "book_quantity": 22,
        "safety_stock": 15,
        "target_stock": 30,
        "is_demo": True,
    },
    {
        "sku": "DEMO-S3-USB-16G",
        "item_name": "16GB 演示储存装置（脱敏）",
        "category": "资讯耗材",
        "location": "DEMO-STORE-C",
        "book_quantity": 3,
        "safety_stock": 3,
        "target_stock": 8,
        "is_demo": True,
    },
    {
        "sku": "DEMO-S3-CABLE-TIE",
        "item_name": "束线带（脱敏）",
        "category": "资讯耗材",
        "location": "DEMO-STORE-C",
        "book_quantity": 50,
        "safety_stock": 20,
        "target_stock": 50,
        "is_demo": True,
    },
    {
        "sku": "DEMO-S3-WHITEBOARD-ERASER",
        "item_name": "白板擦（脱敏）",
        "category": "教学耗材",
        "location": "DEMO-STORE-A",
        "book_quantity": 6,
        "safety_stock": 4,
        "target_stock": 10,
        "is_demo": True,
    },
    {
        "sku": "DEMO-S3-CHALK-WHITE",
        "item_name": "白色粉笔（脱敏）",
        "category": "教学耗材",
        "location": "DEMO-STORE-A",
        "book_quantity": 13,
        "safety_stock": 10,
        "target_stock": 25,
        "is_demo": True,
    },
)


def main() -> int:
    settings = Settings.from_env()
    settings.validate()
    if settings.app_env == "production":
        print("Refusing to seed S3 Demo data in production.", file=sys.stderr)
        return 2
    if settings.auth_mode != "session" or not settings.database_url:
        print("S3 Demo seed requires AUTH_MODE=session and DATABASE_URL.", file=sys.stderr)
        return 2
    if make_url(settings.database_url).database != EXPECTED_DATABASE:
        print("Refusing to seed a database other than puiying_steven_demo.", file=sys.stderr)
        return 2
    if settings.ocr_enabled or settings.ai_structuring_enabled:
        print("S3 Demo seed requires offline OCR/AI.", file=sys.stderr)
        return 2

    application = create_app(settings)
    if not isinstance(application.state.inventory_application, LazyPostgresInventoryApplication):
        print("S3 Demo seed refuses an in-memory inventory repository.", file=sys.stderr)
        return 3
    with application.state.postgres_engine.connect() as connection:
        actor = connection.exec_driver_sql(
            """
            SELECT u.id
              FROM users u
              JOIN user_roles ur ON ur.user_id=u.id
              JOIN roles r ON r.id=ur.role_id
             WHERE u.status='active'
               AND r.status='active'
               AND r.code='operator'
             ORDER BY u.created_at,u.id
             LIMIT 1
            """
        ).scalar_one_or_none()
    if actor is None:
        print("No active Steven user is available for controlled S3 Demo ownership.", file=sys.stderr)
        return 3

    inventory = application.state.inventory_application
    existing = {normalize_sku(item.sku)[1] for item in inventory.list_items()}
    created = 0
    for values in DEMO_ITEMS:
        normalized = normalize_sku(values["sku"])[1]
        if normalized in existing:
            continue
        inventory.create_item(InventoryItemCreateRequest(**values), actor)
        existing.add(normalized)
        created += 1
    print(f"S3 Demo inventory ready: {len(DEMO_ITEMS)} controlled items, {created} newly created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
