from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.api_response import ApiError
from app.modules.document_intelligence.adapters import load_deepseek_api_key


InventorySmartField = Literal["item", "item_code", "specification", "qty", "unit", "location", "safety_stock", "target_stock", "remark"]


class InventorySmartMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mapping: dict[str, InventorySmartField]
    unmapped_columns: list[str] = Field(default_factory=list)


class InventoryQuickEntryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item: str = Field(min_length=1, max_length=250)
    location: str | None = Field(default=None, min_length=1, max_length=200)
    qty: int = Field(ge=0)
    unit: str | None = Field(default=None, max_length=50)

    @field_validator("item")
    @classmethod
    def strip_required(cls, value: str) -> str:
        return value.strip()

    @field_validator("location")
    @classmethod
    def strip_optional_location(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class InventoryQuickEntryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[InventoryQuickEntryItem] = Field(min_length=1, max_length=50)


class QuoteAiRankingEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=250)
    score: int = Field(ge=0, le=100)
    pros: list[str] = Field(default_factory=list, max_length=10)
    cons: list[str] = Field(default_factory=list, max_length=10)


class QuoteAiRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recommendation: str = Field(min_length=1, max_length=250)
    reason: str = Field(min_length=1, max_length=3000)
    ranking: list[QuoteAiRankingEntry] = Field(min_length=1, max_length=20)


class InquiryDraftResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=6000)


class StevenAiAssistService:
    def __init__(self, *, enabled: bool, provider: str, endpoint: str, model: str, timeout_seconds: int, transport: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
        self.enabled = enabled
        self.provider = provider
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._transport = transport

    def smart_inventory_mapping(self, headers: list[str], samples: list[dict[str, Any]]) -> InventorySmartMapping:
        self._require_enabled()
        if self.provider == "mock":
            return self._mock_inventory_mapping(headers)
        payload = self._call_json(
            "你是库存 Excel 列映射助手。只返回 JSON，不得生成正式库存值。",
            {
                "system_fields": {
                    "item": "品项名称", "item_code": "SKU 或物资编码", "specification": "规格或类别描述",
                    "qty": "当前账面数量", "unit": "计量单位", "location": "库位",
                    "safety_stock": "安全库存", "target_stock": "目标库存", "remark": "备注",
                },
                "headers": headers, "sample_rows": samples[:5],
                "instructions": [
                    "只映射可直接写入库存品项的原始字段。",
                    "低库存、建议补货、状态、脱敏标记、创建时间和更新时间属于派生或系统字段，必须保持未映射。",
                ],
                "response_schema": {"mapping": {"原始列名": "system_field"}, "unmapped_columns": ["原始列名"]},
            },
        )
        result = InventorySmartMapping.model_validate(payload)
        if set(result.mapping) - set(headers):
            raise ApiError(502, "ai_mapping_invalid", "AI 返回了不存在的 Excel 列。")
        return result

    def quick_inventory_entry(self, text: str) -> InventoryQuickEntryResult:
        self._require_enabled()
        if self.provider == "mock":
            return self._mock_quick_entry(text)
        payload = self._call_json(
            "你是库存快速录入解析助手。只提取用户明确给出的品项、库位、数量和单位，不得补造 SKU、库位或审批决定。用户未提供库位时必须返回 null，留给人工补充。只返回 JSON。",
            {
                "text": text,
                "response_schema": {"items": [{"item": "string", "location": "string|null", "qty": 0, "unit": "string|null"}]},
            },
        )
        return InventoryQuickEntryResult.model_validate(payload)

    def recommend_quote(self, quote: dict[str, Any]) -> QuoteAiRecommendation:
        self._require_enabled()
        if self.provider == "mock":
            return self._mock_quote_recommendation(quote)
        payload = self._call_json(
            "你是采购比价分析助手。只能分析当前报价的价格、有效期和完整性，结果仅供人工参考；不得批准、下单或修改业务数据。只返回 JSON。",
            {
                "subject": quote.get("subject"), "currency": quote.get("currency"),
                "items": quote.get("items", []), "suppliers": quote.get("suppliers", []),
                "offer_lines": quote.get("offer_lines", []), "comparison": quote.get("comparison", {}),
                "response_schema": {
                    "recommendation": "supplier_name", "reason": "string",
                    "ranking": [{"name": "supplier_name", "score": 0, "pros": ["string"], "cons": ["string"]}],
                },
            },
        )
        return QuoteAiRecommendation.model_validate(payload)

    def inquiry_draft(self, supplier_name: str, items: list[str], purpose: str) -> InquiryDraftResult:
        self._require_enabled()
        if self.provider == "mock":
            item_text = "、".join(items) if items else "相關品項"
            return InquiryDraftResult(text=f"敬啟者：\n\n現就「{purpose}」向貴司 {supplier_name} 詢價，涉及品項包括：{item_text}。敬請提供單價、交付期、報價有效期及相關條款，供人工比較。\n\n謝謝。")
        payload = self._call_json(
            "你是行政询价函草稿助手。使用繁体中文生成简短、礼貌、可复制的询价文字；不得声称已发送、下单或批准。只返回 JSON。",
            {"supplier_name": supplier_name, "items": items, "purpose": purpose, "response_schema": {"text": "traditional_chinese_string"}},
        )
        return InquiryDraftResult.model_validate(payload)

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise ApiError(503, "ai_assist_disabled", "AI 增强功能当前已关闭，请改用原有人工流程。")
        if self.provider not in {"mock", "deepseek"}:
            raise ApiError(503, "ai_assist_unavailable", "AI 增强服务尚未配置。")

    def _call_json(self, system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        api_key = load_deepseek_api_key()
        if not api_key:
            raise ApiError(503, "deepseek_secret_unavailable", "DeepSeek 凭据不可用，未执行 AI 请求。")
        try:
            response = self._transport({
                "url": f"{self.endpoint}/chat/completions", "timeout_seconds": self.timeout_seconds,
                "headers": {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                "json": {"model": self.model, "response_format": {"type": "json_object"}, "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, default=str)},
                ]},
            })
            payload = json.loads(response["choices"][0]["message"]["content"])
        except Exception as error:
            raise ApiError(502, "ai_assist_failed", "DeepSeek 请求失败，未写入任何业务数据。") from error
        if not isinstance(payload, dict):
            raise ApiError(502, "ai_assist_invalid_response", "DeepSeek 返回格式无效，未写入任何业务数据。")
        return payload

    @staticmethod
    def _mock_inventory_mapping(headers: list[str]) -> InventorySmartMapping:
        aliases = {
            "item": ("品项", "品名", "物料", "名称", "item", "name"),
            "item_code": ("sku", "编码", "編碼", "物料号", "itemcode", "code"),
            "specification": ("规格", "規格", "类别", "類別", "spec"),
            "qty": ("账面数量", "帳面數量", "库存数量", "庫存數量", "库存数", "庫存數", "qty", "quantity"),
            "unit": ("单位", "單位", "unit"),
            "location": ("库位", "庫位", "位置", "location"),
            "safety_stock": ("安全库存", "安全庫存", "安全量", "safety"),
            "target_stock": ("目标库存", "目標庫存", "目标量", "目標量", "targetstock"),
            "remark": ("备注", "備註", "remark", "note"),
        }
        mapping: dict[str, InventorySmartField] = {}
        for header in headers:
            normalized = re.sub(r"[\s_\-]+", "", header).casefold()
            for field, values in aliases.items():
                if any(re.sub(r"[\s_\-]+", "", value).casefold() in normalized for value in values):
                    mapping[header] = field  # type: ignore[assignment]
                    break
        return InventorySmartMapping(mapping=mapping, unmapped_columns=[header for header in headers if header not in mapping])

    @staticmethod
    def _mock_quick_entry(text: str) -> InventoryQuickEntryResult:
        items: list[InventoryQuickEntryItem] = []
        for raw_line in re.split(r"[\n；;]+", text):
            line = raw_line.strip()
            if not line:
                continue
            qty_matches = list(re.finditer(r"(?P<qty>\d+)\s*(?P<unit>[\u4e00-\u9fffA-Za-z]{0,8})", line))
            location_match = re.search(r"(?:库位|庫位|位置)\s*[:：]?\s*(?P<location>[A-Za-z0-9_\-\u4e00-\u9fff]+)", line)
            if not qty_matches:
                continue
            qty_match = qty_matches[-1]
            item = line[:qty_match.start()].strip(" ，,：:")
            if item:
                items.append(InventoryQuickEntryItem(
                    item=item,
                    location=location_match.group("location") if location_match else None,
                    qty=int(qty_match.group("qty")),
                    unit=qty_match.group("unit") or None,
                ))
        if not items:
            raise ApiError(422, "quick_entry_unrecognized", "未能识别品项和数量，请按“品项 20包”输入；库位可在解析后人工补充。")
        return InventoryQuickEntryResult(items=items)

    @staticmethod
    def _mock_quote_recommendation(quote: dict[str, Any]) -> QuoteAiRecommendation:
        ranking = quote.get("comparison", {}).get("ranking", [])
        if not ranking:
            raise ApiError(409, "quote_comparison_incomplete", "报价数据不完整，暂不能进行 AI 分析。")
        entries = [
            QuoteAiRankingEntry(
                name=str(item.get("supplier_name", "")), score=max(0, 100 - index * 10),
                pros=[f"当前含税总额 {Decimal(str(item.get('total', '0'))):.2f}", "报价资料已进入人工比价范围"],
                cons=["仍须人工核对交付与条款"] if index else [],
            )
            for index, item in enumerate(ranking)
        ]
        return QuoteAiRecommendation(
            recommendation=entries[0].name,
            reason="依据当前完整报价的总额排序生成，仅供人工参考；采纳后仍按原审批流程处理。",
            ranking=entries,
        )
