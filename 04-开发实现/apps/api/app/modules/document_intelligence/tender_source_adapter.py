from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
import unicodedata

from app.modules.document_intelligence.adapters import validate_structured_candidate
from app.modules.document_intelligence.schemas import AiStructuringRequest, AiStructuringResult


class TenderSourceRuleAdapter:
    _date = r"(\d{4}[-年/.]\d{1,2}[-月/.]\d{1,2}日?)"

    def structure(self, request: AiStructuringRequest) -> AiStructuringResult:
        text = self._normalize_text(request.sanitized_text)
        candidate = {
            "title": self._title(text),
            "document_number": self._line(text, ("文书编号", "文書編號", "编号", "編號")),
            "subject": self._line(text, ("事项名称", "事項名稱", "项目名称", "項目名稱")),
            "generated_date": self._date_value(text, ("生成日期", "发出日期", "發出日期")),
            "deadline_date": self._date_value(text, ("截止日期", "提交日期", "截標日期")),
            "budget_min": None,
            "budget_max": None,
            "location": self._line(text, ("地点", "地點", "服务地点", "服務地點")),
            "supplier_names": self._suppliers(text),
            "controlled_clauses": self._line(text, ("受控条款", "受控條款", "服务要求", "服務要求", "条款", "條款")),
            "uncertain_fields": [],
        }
        candidate["budget_min"], candidate["budget_max"] = self._budget(text)
        required = ("title", "document_number", "subject", "generated_date", "deadline_date", "budget_min", "budget_max", "location", "controlled_clauses")
        candidate["uncertain_fields"] = [field for field in required if candidate[field] in {None, ""}]
        if not candidate["supplier_names"]:
            candidate["uncertain_fields"].append("supplier_names")
        validated = validate_structured_candidate(request.schema_name, candidate)
        warnings = [f"needs_confirmation:{field}" for field in validated["uncertain_fields"]]
        return AiStructuringResult(provider="rules", model="tender-source-regex-v2", candidate=validated, warnings=warnings, source="live")

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized = unicodedata.normalize("NFKC", text)
        normalized = normalized.replace("\u00a0", " ").replace("↵", "")
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in normalized.splitlines()]
        return "\n".join(line for line in lines if line)

    @staticmethod
    def _title(text: str) -> str | None:
        labelled = TenderSourceRuleAdapter._line(text, ("标题", "標題"))
        if labelled:
            return labelled
        for line in text.splitlines():
            value = line.strip()
            if re.search(r"(?:邀请|邀請|征集|徵集|报价|報價|标书|標書|文书|文書)", value) and not re.search(r"[:：]", value):
                return value
        return None

    @staticmethod
    def _line(text: str, labels: tuple[str, ...]) -> str | None:
        joined = "|".join(re.escape(label) for label in labels)
        match = re.search(rf"^(?:{joined})\s*[:：]\s*(.*)$", text, re.IGNORECASE | re.MULTILINE)
        if not match:
            return None
        inline_value = match.group(1).strip()
        if inline_value:
            return inline_value
        for line in text[match.end():].splitlines():
            value = line.strip()
            if value and len(value) > 1:
                return value
        return None

    def _date_value(self, text: str, labels: tuple[str, ...]) -> str | None:
        joined = "|".join(re.escape(label) for label in labels)
        match = re.search(rf"(?:{joined})\s*[:：]?\s*{self._date}", text, re.IGNORECASE)
        if not match:
            return None
        return re.sub(r"[年/.]", "-", match.group(1)).replace("月", "-").replace("日", "")

    @staticmethod
    def _budget(text: str) -> tuple[Decimal | None, Decimal | None]:
        match = re.search(r"(?:预算|預算|金额|金額)[^\d]{0,20}([\d,]+(?:\.\d{1,2})?)\s*(?:-|至|到|—|~)\s*([\d,]+(?:\.\d{1,2})?)", text, re.IGNORECASE)
        if not match:
            return None, None
        try:
            return Decimal(match.group(1).replace(",", "")), Decimal(match.group(2).replace(",", ""))
        except InvalidOperation:
            return None, None

    @staticmethod
    def _suppliers(text: str) -> list[str]:
        match = re.search(r"(?:供应商|供應商|受邀单位|受邀單位)(?:列表)?\s*[:：]\s*([^\r\n]+)", text, re.IGNORECASE)
        if match:
            values = re.split(r"[、,，;；]", match.group(1))
            suppliers = [value.strip(" -—–•·\t") for value in values if value.strip(" -—–•·\t")]
            if suppliers:
                return suppliers

        lines = [line.strip() for line in text.splitlines()]
        suppliers: list[str] = []
        collecting = False
        for line in lines:
            if re.match(r"^(?:供应商|供應商|受邀单位|受邀單位)(?:列表)?\s*[:：]?\s*$", line, re.IGNORECASE):
                collecting = True
                continue
            bullet = re.match(r"^(?:[-—–•·]|\d+[.)、])\s*(.+)$", line)
            if bullet:
                value = bullet.group(1).strip()
                if TenderSourceRuleAdapter._looks_like_supplier(value):
                    suppliers.append(value)
                    collecting = True
                    continue
            if collecting and suppliers:
                break

        if len(suppliers) >= 2:
            return list(dict.fromkeys(suppliers))
        return []

    @staticmethod
    def _looks_like_supplier(value: str) -> bool:
        if not value or len(value) > 120 or re.search(r"[:：@]", value):
            return False
        if re.search(r"(?:条款|條款|要求|联系人|聯絡人|邮箱|郵箱|日期|预算|預算|地点|地點)", value):
            return False
        return bool(re.search(r"(?:供应商|供應商|公司|机构|機構|单位|單位|中心|商行|甲|乙|丙|丁)$", value))
