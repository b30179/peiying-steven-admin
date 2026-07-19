from __future__ import annotations

import argparse
from io import BytesIO
import os
from pathlib import Path
import sys
from uuid import uuid4

from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = PROJECT_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.modules.document_intelligence.adapters import (  # noqa: E402
    DeepSeekStructuringAdapter,
    MockAiStructuringAdapter,
    httpx_json_transport,
    load_deepseek_api_key,
)
from app.modules.document_intelligence.paddle_ocr_adapter import PaddleOcrAdapter  # noqa: E402
from app.modules.document_intelligence.schemas import (  # noqa: E402
    AiStructuringRequest,
    OcrRequest,
)


def build_demo_quote_png() -> bytes:
    lines = [
        "SANITIZED DEMO QUOTATION",
        "Supplier Code: SUP-DEMO-SCAN",
        "Supplier Name: Demo Stationery Supplier (Redacted)",
        "Quote Date: 2026-07-18",
        "Valid Until: 2026-08-18",
        "Currency: HKD",
        "Freight: 0.00",
        "Tax: 0.00",
        "Item Code: DEMO-A4",
        "Item: A4 Copy Paper (Redacted)",
        "Specification: 80gsm, 500 sheets",
        "Quantity: 10",
        "Unit: pack",
        "Unit Price: 42.00",
    ]
    font_path = Path(r"C:\Windows\Fonts\arial.ttf")
    font = ImageFont.truetype(str(font_path), 30) if font_path.exists() else ImageFont.load_default()
    image = Image.new("RGB", (1500, 1050), "white")
    draw = ImageDraw.Draw(image)
    y = 45
    for line in lines:
        draw.text((55, y), line, fill="black", font=font)
        y += 65
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def expected_mock_candidate() -> dict:
    return {
        "quotes": [
            {
                "supplier_code": "SUP-DEMO-SCAN",
                "supplier_name": "Demo Stationery Supplier (Redacted)",
                "quote_date": "2026-07-18",
                "currency": "HKD",
                "valid_until": "2026-08-18",
                "freight": 0,
                "tax": 0,
                "items": [
                    {
                        "item_code": "DEMO-A4",
                        "item": "A4 Copy Paper (Redacted)",
                        "specification": "80gsm, 500 sheets",
                        "qty": 10,
                        "unit": "pack",
                        "unit_price": 42,
                    }
                ],
            }
        ]
    }


def assert_candidate_complete(candidate: dict) -> None:
    if set(candidate) != {"quotes"} or not candidate["quotes"]:
        raise RuntimeError("quotation_schema_incomplete")
    required = {"supplier_code", "supplier_name", "quote_date", "currency", "valid_until", "freight", "tax", "items"}
    item_required = {"item_code", "item", "specification", "qty", "unit", "unit_price"}
    for quote in candidate["quotes"]:
        if set(quote) != required or not quote["items"]:
            raise RuntimeError("quotation_supplier_schema_incomplete")
        if any(set(item) != item_required for item in quote["items"]):
            raise RuntimeError("quotation_item_schema_incomplete")


def run(live_deepseek: bool) -> None:
    os.chdir(API_ROOT)
    request_id = f"d2-smoke-{uuid4()}"
    image_content = build_demo_quote_png()
    ocr = PaddleOcrAdapter()
    ocr_result = ocr.extract(
        OcrRequest(
            file_id="sanitized-demo-quote.png",
            document_type="supplier_quotation",
            purpose="quotation_extraction",
            request_id=request_id,
            content=image_content,
            mime_type="image/png",
        )
    )
    if not ocr_result.text.strip() or not ocr_result.evidence:
        raise RuntimeError("paddle_ocr_returned_no_text")
    if any(entry.page != 1 or len(entry.bbox) < 4 or not 0 <= entry.confidence <= 1 for entry in ocr_result.evidence):
        raise RuntimeError("paddle_ocr_evidence_invalid")
    print(f"OCR_OK provider={ocr_result.provider} model={ocr_result.model} chars={len(ocr_result.text)} evidence={len(ocr_result.evidence)}")

    ai_request = AiStructuringRequest(
        document_type="supplier_quotation",
        purpose="quotation_extraction",
        schema_name="steven.s2.quotation",
        schema_version="1.0",
        request_id=request_id,
        sanitized_text=ocr_result.text,
        evidence=ocr_result.evidence,
    )
    mock_result = MockAiStructuringAdapter(expected_mock_candidate()).structure(ai_request)
    assert_candidate_complete(mock_result.candidate)
    print(f"AI_MOCK_OK provider={mock_result.provider} model={mock_result.model} suppliers={len(mock_result.candidate['quotes'])}")

    if not live_deepseek:
        print("AI_LIVE_SKIPPED explicit flag not supplied")
        return
    if not load_deepseek_api_key():
        raise RuntimeError("deepseek_secret_unavailable")
    live_result = DeepSeekStructuringAdapter(
        endpoint="https://api.deepseek.com/v1",
        model="deepseek-chat",
        timeout_seconds=60,
        transport=httpx_json_transport,
    ).structure(ai_request)
    assert_candidate_complete(live_result.candidate)
    print(f"AI_LIVE_OK provider={live_result.provider} model={live_result.model} suppliers={len(live_result.candidate['quotes'])}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the sanitized local PaddleOCR and optional DeepSeek quotation pipeline smoke test.")
    parser.add_argument("--live-deepseek", action="store_true", help="Perform one sanitized live DeepSeek request using the approved server-side secret source.")
    args = parser.parse_args()
    try:
        run(args.live_deepseek)
    except Exception as error:
        print(f"PIPELINE_FAILED type={type(error).__name__}", file=sys.stderr)
        return 1
    print("PIPELINE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
