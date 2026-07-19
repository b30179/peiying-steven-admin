from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "demo-data" / "steven-d0"
FONT_PATH = Path("C:/Windows/Fonts/simhei.ttf")
ARIAL_PATH = Path("C:/Windows/Fonts/arial.ttf")

ITEMS = [
    ("ITEM-001", "A4 影印纸", "A4 Copy Paper", "80gsm, 500 sheets/pack", "20", "包 / pack"),
    ("ITEM-002", "蓝色原子笔", "Blue Ball Pen", "0.7mm", "100", "支 / pc"),
    ("ITEM-003", "订书钉", "Staples", "24/6, 1000/box", "50", "盒 / box"),
    ("ITEM-004", "A4 文件夹", "A4 File Folder", "transparent, 40 pages", "60", "个 / pc"),
    ("ITEM-005", "白板笔", "Whiteboard Marker", "black, erasable", "30", "支 / pc"),
]

SUPPLIERS = [
    {
        "supplier_code": "SUP-A",
        "supplier_name": "文具供应商甲（脱敏）",
        "supplier_name_en": "Sanitized Stationery Supplier A",
        "valid_until": "2026-08-15",
        "freight": "120",
        "tax": "80",
        "prices": ["42", "4.2", "8.5", "6", "12"],
    },
    {
        "supplier_code": "SUP-B",
        "supplier_name": "文具供应商乙（脱敏）",
        "supplier_name_en": "Sanitized Stationery Supplier B",
        "valid_until": "2026-08-20",
        "freight": "180",
        "tax": "75",
        "prices": ["40", "4.5", "8", "6.2", "11.5"],
    },
    {
        "supplier_code": "SUP-C",
        "supplier_name": "文具供应商丙（脱敏）",
        "supplier_name_en": "Sanitized Stationery Supplier C",
        "valid_until": "2026-08-10",
        "freight": "90",
        "tax": "100",
        "prices": ["43", "4", "8.2", "5.8", "12.5"],
    },
]


def candidate(supplier: dict[str, Any], *, currency: str = "HKD", valid_until: str | None = None, item_count: int = 5) -> dict[str, Any]:
    return {
        "supplier_code": supplier["supplier_code"],
        "supplier_name": supplier["supplier_name"],
        "currency": currency,
        "valid_until": valid_until or supplier["valid_until"],
        "freight": supplier["freight"],
        "tax": supplier["tax"],
        "items": [
            {
                "item_code": item[0],
                "item": item[1],
                "specification": item[3],
                "qty": item[4],
                "unit": item[5].split(" / ")[0],
                "unit_price": supplier["prices"][index],
            }
            for index, item in enumerate(ITEMS[:item_count])
        ],
    }


def image_fonts() -> tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont, ImageFont.FreeTypeFont]:
    return (
        ImageFont.truetype(str(FONT_PATH), 42),
        ImageFont.truetype(str(FONT_PATH), 25),
        ImageFont.truetype(str(FONT_PATH), 20),
    )


def draw_raster_quote(path: Path, supplier: dict[str, Any], *, currency: str = "HKD", valid_until: str | None = None, item_count: int = 5, bilingual: bool = False) -> Path:
    width, height = 1654, 2339
    image = Image.new("RGB", (width, height), "#f7f7f4")
    draw = ImageDraw.Draw(image)
    title_font, body_font, small_font = image_fonts()
    margin = 105
    draw.text((margin, 75), "书面报价单 / QUOTATION" if bilingual else "书面报价单", font=title_font, fill="#151515")
    draw.text((margin, 145), "完全脱敏演示资料 / SANITIZED DEMO DATA", font=small_font, fill="#9b1c1c")
    supplier_label = f"供应商：{supplier['supplier_name']} ({supplier['supplier_code']})"
    if bilingual:
        supplier_label += f"\nSupplier: {supplier['supplier_name_en']}"
    draw.multiline_text((margin, 215), supplier_label, font=body_font, fill="#252525", spacing=8)
    draw.text((margin, 305 if bilingual else 270), f"币种 / Currency: {currency}    有效期 / Valid until: {valid_until or supplier['valid_until']}", font=body_font, fill="#252525")

    top = 390 if bilingual else 345
    columns = [margin, 255, 650, 950, 1090, 1230, 1390, 1549]
    headers = ["编号", "品项 / Item", "规格 / Specification", "数量", "单位", "单价", "金额"]
    row_height = 145 if bilingual else 125
    table_bottom = top + row_height * (item_count + 1)
    for x in columns:
        draw.line((x, top, x, table_bottom), fill="#333333", width=3)
    draw.line((columns[-1], top, columns[-1], table_bottom), fill="#333333", width=3)
    for row in range(item_count + 2):
        y = top + row_height * row
        draw.line((margin, y, columns[-1], y), fill="#333333", width=3)
    for index, header in enumerate(headers):
        draw.text((columns[index] + 8, top + 34), header, font=small_font, fill="#111111")

    for row_index, item in enumerate(ITEMS[:item_count]):
        price = supplier["prices"][row_index]
        amount = float(item[4]) * float(price)
        values = [item[0], f"{item[1]}\n{item[2]}" if bilingual else item[1], item[3], item[4], item[5], price, f"{amount:.2f}"]
        y = top + row_height * (row_index + 1) + 20
        for column_index, value in enumerate(values):
            draw.multiline_text((columns[column_index] + 8, y), str(value), font=small_font, fill="#111111", spacing=6)

    subtotal = sum(float(item[4]) * float(supplier["prices"][index]) for index, item in enumerate(ITEMS[:item_count]))
    summary_y = table_bottom + 55
    summary = [
        f"品项小计 / Item subtotal: {currency} {subtotal:.2f}",
        f"供应商级运费 / Supplier-level freight: {currency} {supplier['freight']}",
        f"供应商级税费 / Supplier-level tax: {currency} {supplier['tax']}",
        f"合计 / Total: {currency} {subtotal + float(supplier['freight']) + float(supplier['tax']):.2f}",
    ]
    for line in summary:
        draw.text((880, summary_y), line, font=body_font, fill="#151515")
        summary_y += 54
    draw.text((margin, 2180), "本文件不含真实姓名、公司、电话、电邮、地址、银行、校务或学生资料。", font=small_font, fill="#555555")

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".png":
        image.save(path, optimize=True)
    else:
        scan = ImageEnhance.Contrast(image).enhance(0.93).rotate(0.15, fillcolor="#f7f7f4")
        scan.save(path, "PDF", resolution=150.0)
    return path


def draw_vector_quote(path: Path, supplier: dict[str, Any]) -> Path:
    pdfmetrics.registerFont(TTFont("DemoChinese", str(FONT_PATH)))
    pdfmetrics.registerFont(TTFont("DemoArial", str(ARIAL_PATH)))
    page_width, page_height = A4
    document = canvas.Canvas(str(path), pagesize=A4)
    document.setTitle("Sanitized Demo Quotation")
    document.setFont("DemoArial", 20)
    document.drawString(48, page_height - 58, "QUOTATION /")
    document.setFont("DemoChinese", 20)
    document.drawString(178, page_height - 58, "书面报价单")
    document.setFont("DemoChinese", 9)
    document.setFillColorRGB(0.62, 0.08, 0.08)
    document.drawString(48, page_height - 78, "完全脱敏演示资料 / SANITIZED DEMO DATA")
    document.setFillColorRGB(0.1, 0.1, 0.1)
    document.setFont("DemoChinese", 11)
    document.drawString(48, page_height - 108, f"供应商 / Supplier: {supplier['supplier_name']} ({supplier['supplier_code']})")
    document.setFont("DemoArial", 10)
    document.drawString(48, page_height - 128, f"Currency: HKD    Valid until: {supplier['valid_until']}    Ref: DEMO-20260717-B")

    x_positions = [48, 105, 225, 350, 390, 430, 490, 548]
    headers = ["Code", "Item", "Spec", "Qty", "Unit", "Unit price", "Amount"]
    table_top = page_height - 165
    row_height = 55
    for row in range(7):
        y = table_top - row * row_height
        document.line(x_positions[0], y, x_positions[-1], y)
    for x in x_positions:
        document.line(x, table_top, x, table_top - 6 * row_height)
    for index, header in enumerate(headers):
        document.setFont("DemoArial", 8)
        document.drawString(x_positions[index] + 4, table_top - 20, header)
    for row_index, item in enumerate(ITEMS):
        price = supplier["prices"][row_index]
        amount = float(item[4]) * float(price)
        values = [item[0], item[2], item[3], item[4], item[5].split(" / ")[-1], price, f"{amount:.2f}"]
        y = table_top - (row_index + 1) * row_height - 19
        for column_index, value in enumerate(values):
            document.setFont("DemoArial", 7.5)
            document.drawString(x_positions[column_index] + 4, y, str(value)[:25])
        document.setFont("DemoChinese", 7.5)
        document.drawString(x_positions[1] + 4, y - 13, item[1])

    subtotal = sum(float(item[4]) * float(supplier["prices"][index]) for index, item in enumerate(ITEMS))
    summary_y = table_top - 6 * row_height - 35
    document.setFont("DemoArial", 10)
    for line in (
        f"Item subtotal: HKD {subtotal:.2f}",
        f"Supplier-level freight: HKD {supplier['freight']}",
        f"Supplier-level tax: HKD {supplier['tax']}",
        f"Total: HKD {subtotal + float(supplier['freight']) + float(supplier['tax']):.2f}",
    ):
        document.drawRightString(548, summary_y, line)
        summary_y -= 18
    document.setFont("DemoChinese", 8)
    document.drawString(48, 42, "本文件不含真实身份、联系方式、银行、校务或学生资料。")
    document.save()
    return path


def write_ground_truth(stem: str, payload: dict[str, Any], expected: str, warnings: list[str] | None = None) -> str:
    filename = f"{stem}.ground-truth.json"
    data = {
        "classification": "fully_sanitized_demo_data",
        "schema_name": "steven.s2.quotation",
        "schema_version": "1.0",
        "expected_result": expected,
        "warnings": warnings or [],
        "candidate": payload,
    }
    (OUTPUT / filename).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return filename


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    artifacts: list[dict[str, Any]] = []

    normal_a = "01_supplier_a_zh_scanned"
    draw_raster_quote(OUTPUT / f"{normal_a}.pdf", SUPPLIERS[0])
    artifacts.append({"file": f"{normal_a}.pdf", "format": "chinese_scanned_pdf", "ground_truth": write_ground_truth(normal_a, candidate(SUPPLIERS[0]), "needs_review_then_confirmable")})

    normal_b = "02_supplier_b_mixed_numbers"
    draw_vector_quote(OUTPUT / f"{normal_b}.pdf", SUPPLIERS[1])
    artifacts.append({"file": f"{normal_b}.pdf", "format": "english_chinese_mixed_pdf", "ground_truth": write_ground_truth(normal_b, candidate(SUPPLIERS[1]), "needs_review_then_confirmable")})

    normal_c = "03_supplier_c_bilingual_table"
    draw_raster_quote(OUTPUT / f"{normal_c}.png", SUPPLIERS[2], bilingual=True)
    draw_raster_quote(OUTPUT / f"{normal_c}.pdf", SUPPLIERS[2], bilingual=True)
    artifacts.append({"file": f"{normal_c}.png", "companion_pdf": f"{normal_c}.pdf", "format": "bilingual_table_png_pdf", "ground_truth": write_ground_truth(normal_c, candidate(SUPPLIERS[2]), "needs_review_then_confirmable")})

    missing = "04_exception_missing_item"
    draw_raster_quote(OUTPUT / f"{missing}.pdf", SUPPLIERS[1], item_count=4, bilingual=True)
    artifacts.append({"file": f"{missing}.pdf", "format": "exception_missing_item", "ground_truth": write_ground_truth(missing, candidate(SUPPLIERS[1], item_count=4), "blocked_on_confirm", ["candidate_item_set_mismatch"])})

    currency = "05_exception_currency_conflict"
    draw_raster_quote(OUTPUT / f"{currency}.pdf", SUPPLIERS[2], currency="USD", bilingual=True)
    artifacts.append({"file": f"{currency}.pdf", "format": "exception_currency_conflict", "ground_truth": write_ground_truth(currency, candidate(SUPPLIERS[2], currency="USD"), "blocked_on_confirm", ["candidate_currency_mismatch"])})

    expired = "06_exception_expired_quote"
    draw_raster_quote(OUTPUT / f"{expired}.pdf", SUPPLIERS[0], valid_until="2020-01-01", bilingual=True)
    artifacts.append({"file": f"{expired}.pdf", "format": "exception_expired_quote", "ground_truth": write_ground_truth(expired, candidate(SUPPLIERS[0], valid_until="2020-01-01"), "needs_review_then_confirmable_with_warning", ["expired_quote"])})

    manifest = {
        "dataset": "Steven Demo D0 sanitized quotation fixtures",
        "version": "1.0",
        "generated_on": "2026-07-17",
        "classification": "fully_sanitized_demo_data",
        "currency_baseline": "HKD",
        "normal_baseline": "3 suppliers x 5 items = 15 offer lines",
        "contains_real_data": False,
        "artifacts": artifacts,
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "artifacts": len(artifacts)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
