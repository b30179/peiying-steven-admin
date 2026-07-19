from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path
from threading import RLock
from typing import Any

import numpy as np
from PIL import Image

from app.modules.document_intelligence.schemas import EvidenceLocation, OcrRequest, OcrResult


class PaddleOcrAdapter:
    def __init__(self, model_root: str = "models/ocr/official_models") -> None:
        self.model_root = Path(model_root)
        self._engine: Any | None = None
        self._lock = RLock()

    def extract(self, request: OcrRequest) -> OcrResult:
        pages = self._decode_pages(request.content, request.mime_type)
        evidence: list[EvidenceLocation] = []
        text_lines: list[str] = []
        with self._lock:
            engine = self._get_engine()
            for page_number, image in enumerate(pages, start=1):
                for result in engine.predict(np.asarray(image.convert("RGB"))):
                    payload = self._result_payload(result)
                    texts = payload.get("rec_texts") or []
                    scores = payload.get("rec_scores") or []
                    polygons = payload.get("rec_polys")
                    if polygons is None or len(polygons) == 0:
                        polygons = payload.get("dt_polys")
                    if polygons is None:
                        polygons = []
                    for line_index, raw_text in enumerate(texts):
                        text = str(raw_text).strip()
                        if not text:
                            continue
                        score = float(scores[line_index]) if line_index < len(scores) else 0.0
                        polygon = polygons[line_index] if line_index < len(polygons) else [0, 0, 0, 0]
                        bbox = self._flatten_bbox(polygon)
                        text_lines.append(text)
                        evidence.append(
                            EvidenceLocation(
                                field_path=f"document.pages[{page_number - 1}].lines[{line_index}]",
                                page=page_number,
                                original_text=text,
                                bbox=bbox,
                                confidence=max(0.0, min(1.0, score)),
                            )
                        )
        warnings = [] if text_lines else ["ocr_no_text_detected"]
        return OcrResult(
            provider="paddle",
            model="PP-OCRv5-mobile",
            text="\n".join(text_lines),
            evidence=evidence,
            warnings=warnings,
            source="live",
        )

    def _get_engine(self):
        if self._engine is not None:
            return self._engine
        os.environ.setdefault("PADDLE_PDX_CACHE_HOME", "models/ocr")
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        from paddleocr import PaddleOCR

        self._engine = PaddleOCR(
            text_detection_model_name="PP-OCRv5_mobile_det",
            text_detection_model_dir=str(self.model_root / "PP-OCRv5_mobile_det"),
            text_recognition_model_name="PP-OCRv5_mobile_rec",
            text_recognition_model_dir=str(self.model_root / "PP-OCRv5_mobile_rec"),
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
        return self._engine

    @staticmethod
    def _decode_pages(content: bytes, mime_type: str) -> list[Image.Image]:
        if mime_type == "application/pdf":
            import pypdfium2 as pdfium

            document = pdfium.PdfDocument(content)
            try:
                return [page.render(scale=2).to_pil().convert("RGB") for page in document]
            finally:
                document.close()
        if mime_type not in {"image/png", "image/jpeg"}:
            raise ValueError("unsupported_paddle_document_type")
        with Image.open(BytesIO(content)) as image:
            return [image.convert("RGB")]

    @staticmethod
    def _result_payload(result: Any) -> dict[str, Any]:
        value = result.json if hasattr(result, "json") else result
        if callable(value):
            value = value()
        if isinstance(value, dict) and isinstance(value.get("res"), dict):
            return value["res"]
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _flatten_bbox(polygon: Any) -> list[float]:
        array = np.asarray(polygon, dtype=float).reshape(-1)
        values = [float(value) for value in array[:8]]
        return values if len(values) >= 4 else [0.0, 0.0, 0.0, 0.0]
