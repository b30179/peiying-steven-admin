from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image
from starlette.datastructures import Headers, UploadFile

from app.core.api_response import ApiError, REQUEST_ID_PATTERN
from app.modules.document_intelligence.adapters import validate_structured_candidate
from app.modules.document_intelligence.paddle_ocr_adapter import PaddleOcrAdapter
from app.modules.document_intelligence.schemas import AiStructuringRequest
from app.modules.document_intelligence.tender_source_adapter import TenderSourceRuleAdapter
from app.modules.document_intelligence.router import _validated_upload


def image_bytes(image_format: str, *, color: str = "white") -> bytes:
    output = BytesIO()
    Image.new("RGB", (64, 48), color=color).save(output, format=image_format)
    return output.getvalue()


def upload(filename: str, content_type: str) -> UploadFile:
    return UploadFile(file=BytesIO(), filename=filename, headers=Headers({"content-type": content_type}))


@pytest.mark.parametrize(
    ("filename", "content_type", "content", "expected_mime"),
    [
        ("scan.png", "image/png", image_bytes("PNG"), "image/png"),
        ("scan.jpg", "image/jpeg", image_bytes("JPEG"), "image/jpeg"),
        ("scan.jpeg", "application/octet-stream", image_bytes("JPEG"), "image/jpeg"),
        ("scan.pdf", "application/pdf", b"%PDF-1.7\n% sanitized fixture", "application/pdf"),
    ],
)
def test_validated_upload_accepts_supported_magic_bytes(filename, content_type, content, expected_mime):
    assert _validated_upload(upload(filename, content_type), content) == (filename, expected_mime)


@pytest.mark.parametrize(
    ("filename", "content_type", "content", "code"),
    [
        ("empty.png", "image/png", b"", "empty_file"),
        ("scan.txt", "text/plain", b"fixture", "unsupported_document_type"),
        ("scan.png", "image/jpeg", image_bytes("PNG"), "unsupported_document_type"),
        ("scan.jpg", "image/jpeg", image_bytes("PNG"), "document_signature_mismatch"),
        ("scan.pdf", "application/pdf", b"not-a-pdf", "document_signature_mismatch"),
    ],
)
def test_validated_upload_rejects_invalid_files(filename, content_type, content, code):
    with pytest.raises(ApiError) as captured:
        _validated_upload(upload(filename, content_type), content)
    assert captured.value.code == code


def test_validated_upload_rejects_files_over_ten_megabytes():
    content = b"\x89PNG\r\n\x1a\n" + b"x" * (10 * 1024 * 1024)
    with pytest.raises(ApiError) as captured:
        _validated_upload(upload("scan.png", "image/png"), content)
    assert captured.value.code == "file_too_large"


def test_paddle_decoder_supports_png_jpeg_and_multi_page_pdf():
    png_pages = PaddleOcrAdapter._decode_pages(image_bytes("PNG"), "image/png")
    jpeg_pages = PaddleOcrAdapter._decode_pages(image_bytes("JPEG"), "image/jpeg")

    pdf = BytesIO()
    first = Image.new("RGB", (64, 48), color="white")
    second = Image.new("RGB", (64, 48), color="lightgray")
    first.save(pdf, format="PDF", save_all=True, append_images=[second])
    pdf_pages = PaddleOcrAdapter._decode_pages(pdf.getvalue(), "application/pdf")

    assert len(png_pages) == 1
    assert len(jpeg_pages) == 1
    assert len(pdf_pages) == 2
    assert all(page.mode == "RGB" for page in [*png_pages, *jpeg_pages, *pdf_pages])


def quotation_candidate() -> dict:
    return {
        "supplier_code": "SUP-DEMO",
        "supplier_name": "Demo Supplier (Redacted)",
        "quote_date": "2026-07-18",
        "currency": "HKD",
        "valid_until": "2026-08-18",
        "freight": 0,
        "tax": 0,
        "items": [{"item_code": "DEMO-A4", "item": "A4 Paper (Redacted)", "specification": "80gsm", "qty": 10, "unit": "pack", "unit_price": 42}],
    }


def test_s2_schema_rejects_ai_decision_fields_and_extra_fields():
    valid = quotation_candidate()
    assert validate_structured_candidate("steven.s2.quotation", valid)["quotes"][0]["supplier_code"] == "SUP-DEMO"

    for forbidden in ["recommend", "rank", "approve", "order", "total", "select_supplier"]:
        invalid = quotation_candidate()
        invalid[forbidden] = "not allowed"
        with pytest.raises(ValueError, match="forbidden_ai_decision_field"):
            validate_structured_candidate("steven.s2.quotation", invalid)


def test_request_id_format_is_bounded_and_safe():
    assert REQUEST_ID_PATTERN.fullmatch("D2.scan-20260718:abc_123")
    assert REQUEST_ID_PATTERN.fullmatch("a" * 128)
    assert not REQUEST_ID_PATTERN.fullmatch("a" * 129)
    assert not REQUEST_ID_PATTERN.fullmatch("bad request id")
    assert not REQUEST_ID_PATTERN.fullmatch("/path-like")


def test_tender_source_rules_extract_bulleted_suppliers_from_real_ocr_layout():
    ocr_text = """采购服务邀请文书
文书编号：DEMO-S1-RETURN-374800222
事项名称：设施保养服务
生成日期：2026-07-17
截止日期：2026-07-20
预算范围：HKD1000.00-2000.00
地点：学校
C
-供应商甲
-供应商乙
-供应商丙
L
受控条款：
仅接受脱敏演示资料；最终内容必须由人工复核。
七
联系人：hs
邮箱：demo-contact@example.invalid
L"""
    result = TenderSourceRuleAdapter().structure(AiStructuringRequest(
        document_type="tender_source",
        purpose="tender_source_extraction",
        schema_name="steven.s1.tender_source",
        schema_version="1.0",
        request_id="request-real-layout",
        sanitized_text=ocr_text,
        evidence=[],
    ))

    assert result.candidate["title"] == "采购服务邀请文书"
    assert result.candidate["supplier_names"] == ["供应商甲", "供应商乙", "供应商丙"]
    assert result.candidate["controlled_clauses"] == "仅接受脱敏演示资料;最终内容必须由人工复核。"
    assert result.candidate["uncertain_fields"] == []
