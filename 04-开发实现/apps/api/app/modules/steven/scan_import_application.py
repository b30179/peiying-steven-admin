from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from typing import Iterator

from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from app.core.api_response import ApiError
from app.modules.document_intelligence.adapters import validate_structured_candidate
from app.modules.document_intelligence.postgres_repository import PostgresDocumentIntelligenceRepository
from app.modules.document_intelligence.repository import InMemoryDocumentIntelligenceRepository
from app.modules.document_intelligence.service import transition_candidate_jobs
from app.modules.steven.postgres_quote_repository import PostgresQuoteAuditRepository, PostgresQuoteRepository
from app.modules.steven.quote_schemas import QuoteItemCreateRequest, QuoteOfferLineCreateRequest, QuoteSupplierCreateRequest
from app.modules.steven.quote_service import StevenQuoteService


class ScanImportTransaction:
    def __init__(self, documents, quote_repository, quote_audit) -> None:
        self.documents = documents
        self.quote_repository = quote_repository
        self.quote_audit = quote_audit


class InMemoryScanImportUnitOfWork:
    def __init__(self, documents, quote_repository, quote_audit) -> None:
        self.documents = documents
        self.quote_repository = quote_repository
        self.quote_audit = quote_audit

    @contextmanager
    def begin(self, candidate_id: str, quote_id: str) -> Iterator[ScanImportTransaction]:
        del candidate_id, quote_id
        checkpoint = self.quote_audit.checkpoint()
        try:
            with self.documents.transaction(), self.quote_repository.transaction():
                yield ScanImportTransaction(self.documents, self.quote_repository, self.quote_audit)
        except Exception:
            self.quote_audit.rollback_to(checkpoint)
            raise


class PostgresScanImportUnitOfWork:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @contextmanager
    def begin(self, candidate_id: str, quote_id: str) -> Iterator[ScanImportTransaction]:
        with self.engine.begin() as connection:
            connection.execute(text("SELECT id FROM review_candidates WHERE id=:id FOR UPDATE"), {"id": candidate_id})
            connection.execute(text("SELECT id FROM steven_quote_jobs WHERE id=:id FOR UPDATE"), {"id": quote_id})
            yield ScanImportTransaction(
                PostgresDocumentIntelligenceRepository(connection),
                PostgresQuoteRepository(connection),
                PostgresQuoteAuditRepository(connection),
            )


class StevenScanImportApplicationService:
    def __init__(self, unit_of_work, parser, exporter, storage) -> None:
        self.unit_of_work = unit_of_work
        self.parser = parser
        self.exporter = exporter
        self.storage = storage

    def confirm_scan_candidate(self, candidate_id: str, quote_id: str, actor: str):
        try:
            with self.unit_of_work.begin(candidate_id, quote_id) as transaction:
                candidate = transaction.documents.get_candidate(candidate_id)
                if (
                    not candidate
                    or candidate.target_object_type != "steven_quote_job"
                    or candidate.target_object_id != quote_id
                    or candidate.schema_name != "steven.s2.quotation"
                    or candidate.purpose != "quotation_extraction"
                    or not transaction.documents.has_s2_link(candidate_id, quote_id)
                ):
                    raise ApiError(404, "candidate_not_found", "未找到当前采购事项的扫描候选。")
                if candidate.status != "needs_review":
                    raise ApiError(409, "candidate_not_reviewable", "候选已处理或状态不允许确认。")
                try:
                    payload = validate_structured_candidate(candidate.schema_name, candidate.human_revision_json or candidate.candidate_json)
                except ValueError as error:
                    raise ApiError(422, "candidate_payload_invalid", "候选 JSON 不符合报价结构，请修订后再确认。") from error
                service = StevenQuoteService(transaction.quote_repository, transaction.quote_audit, self.parser, self.exporter, self.storage)
                job = service._require_editable_job(quote_id)
                quotes = payload["quotes"]
                supplier_codes = [quote["supplier_code"] for quote in quotes]
                if len(set(supplier_codes)) != len(supplier_codes):
                    raise ApiError(409, "duplicate_supplier_code", "同一次扫描候选中供应商编号不可重复。")
                if any(quote["currency"] != job.currency for quote in quotes):
                    raise ApiError(409, "candidate_currency_mismatch", "候选币种与采购事项币种不一致，禁止写入正式报价。")

                valid_until_by_code: dict[str, date] = {}
                for quote in quotes:
                    if not quote["valid_until"]:
                        raise ApiError(
                            409,
                            "candidate_valid_until_required",
                            "报价文件未提供有效期；请在人工复核 JSON 中为每家供应商填写 valid_until（YYYY-MM-DD）。",
                            {"supplier_code": quote["supplier_code"]},
                        )
                    try:
                        valid_until_by_code[quote["supplier_code"]] = date.fromisoformat(quote["valid_until"])
                    except ValueError as error:
                        raise ApiError(
                            422,
                            "candidate_valid_until_invalid",
                            "报价有效期格式无效；请使用 YYYY-MM-DD。",
                            {"supplier_code": quote["supplier_code"]},
                        ) from error

                canonical_items = {item["item_code"]: item for item in quotes[0]["items"]}
                if len(canonical_items) != len(quotes[0]["items"]):
                    raise ApiError(409, "duplicate_item_code", "同一供应商候选中品项编号不可重复。")
                canonical_item_codes = set(canonical_items)
                for quote in quotes[1:]:
                    quote_items = {item["item_code"]: item for item in quote["items"]}
                    if len(quote_items) != len(quote["items"]):
                        raise ApiError(409, "duplicate_item_code", "同一供应商候选中品项编号不可重复。")
                    if set(quote_items) != canonical_item_codes:
                        raise ApiError(409, "candidate_item_set_mismatch", "多供应商候选的品项集合不一致，禁止写入正式报价。")
                    for item_code, item in quote_items.items():
                        canonical = canonical_items[item_code]
                        if any(item[field] != canonical[field] for field in ("item", "specification", "qty", "unit")):
                            raise ApiError(409, "candidate_item_metadata_mismatch", "多供应商候选的品项名称、规格、数量或单位不一致。")

                existing_items = {item.item_code: item for item in transaction.quote_repository.items_for(quote_id)}
                if existing_items and set(existing_items) != canonical_item_codes:
                    raise ApiError(409, "candidate_item_set_mismatch", "候选品项与采购事项既有标准品项不一致。")
                if not existing_items:
                    for item in quotes[0]["items"]:
                        service.add_item(quote_id, QuoteItemCreateRequest(
                            item_code=item["item_code"], item=item["item"], specification=item["specification"],
                            qty=item["qty"], unit=item["unit"],
                        ), actor)
                    existing_items = {item.item_code: item for item in transaction.quote_repository.items_for(quote_id)}

                for quote in quotes:
                    supplier_view = service.add_supplier(quote_id, QuoteSupplierCreateRequest(
                        supplier_code=quote["supplier_code"], supplier_name=quote["supplier_name"], currency=quote["currency"],
                        valid_until=valid_until_by_code[quote["supplier_code"]], freight=quote["freight"], tax=quote["tax"],
                    ), actor)
                    supplier = next(item for item in supplier_view.suppliers if item.supplier_code == quote["supplier_code"])
                    for item in quote["items"]:
                        service.add_offer(quote_id, QuoteOfferLineCreateRequest(
                            quote_supplier_id=supplier.id,
                            quote_item_id=existing_items[item["item_code"]].id,
                            unit_price=item["unit_price"],
                            remark="经人工复核的 OCR/AI 候选",
                        ), actor)

                candidate.transition("confirmed", actor)
                transition_candidate_jobs(transaction.documents, candidate, "confirmed")
                transaction.documents.save_candidate(candidate)
                if hasattr(transaction.documents, "add_s2_link"):
                    transaction.documents.add_s2_link(candidate.id, quote_id)
                transaction.quote_audit.append(
                    actor=actor,
                    action="quote.scan_candidate_confirm",
                    object_type="steven_quote_job",
                    object_id=quote_id,
                    before_after={
                        "before": {"candidate_status": "needs_review"},
                        "after": {
                            "candidate_id": candidate.id,
                            "candidate_status": "confirmed",
                            "supplier_count": len(supplier_codes),
                            "supplier_codes": supplier_codes,
                        },
                    },
                )
                return service.get_quote(job.id)
        except IntegrityError as error:
            raise ApiError(409, "candidate_write_conflict", "候选确认与其他写入冲突，已回滚，请刷新后重试。") from error
