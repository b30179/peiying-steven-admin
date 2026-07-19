from __future__ import annotations

from pydantic import ValidationError
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from app.core.api_response import ApiError
from app.core.audit import PostgresAuditRepository
from app.modules.document_intelligence.adapters import validate_structured_candidate
from app.modules.document_intelligence.postgres_repository import PostgresDocumentIntelligenceRepository
from app.modules.document_intelligence.service import transition_candidate_jobs
from app.modules.steven.postgres_tender_repository import PostgresTenderRepository
from app.modules.steven.tender_schemas import TenderUpdateRequest
from app.modules.steven.tender_service import StevenTenderService


class TenderScanApplicationService:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def confirm_scan_candidate(self, candidate_id: str, tender_id: str, actor: str, request_id: str, template_id: str | None = None) -> dict:
        try:
            with self.engine.begin() as connection:
                connection.execute(text("SELECT id FROM review_candidates WHERE id=:id FOR UPDATE"), {"id": candidate_id})
                connection.execute(text("SELECT id FROM steven_tender_jobs WHERE id=:id FOR UPDATE"), {"id": tender_id})
                documents = PostgresDocumentIntelligenceRepository(connection)
                candidate = documents.get_candidate(candidate_id)
                if (
                    candidate is None
                    or candidate.target_object_type != "steven_tender_job"
                    or candidate.target_object_id != tender_id
                    or candidate.schema_name != "steven.s1.tender_source"
                    or candidate.purpose != "tender_source_extraction"
                    or not documents.has_s1_link(candidate_id, tender_id)
                ):
                    raise ApiError(404, "candidate_not_found", "未找到当前文书事项的扫描候选。")
                if candidate.status != "needs_review":
                    raise ApiError(409, "candidate_not_reviewable", "候选已处理或状态不允许确认。")
                payload = validate_structured_candidate(
                    candidate.schema_name,
                    candidate.human_revision_json or candidate.candidate_json,
                )
                uncertain_fields = [value for value in payload.pop("uncertain_fields", []) if value]
                if uncertain_fields:
                    raise ApiError(422, "candidate_fields_unconfirmed", "仍有扫描字段待人工确认。", {"fields": uncertain_fields})
                update_values = {key: value for key, value in payload.items() if value is not None}
                if template_id is not None:
                    update_values["template_id"] = template_id
                if not update_values:
                    raise ApiError(422, "candidate_empty", "扫描候选没有可写入的受控字段。")
                update_request = TenderUpdateRequest.model_validate(update_values)
                audit = PostgresAuditRepository(connection)
                service = StevenTenderService(PostgresTenderRepository(connection), audit)
                service.update_tender(tender_id, update_request, actor)
                preview = service.preview(tender_id, actor)
                candidate.transition("confirmed", actor)
                transition_candidate_jobs(documents, candidate, "confirmed")
                documents.save_candidate(candidate)
                documents.add_s1_link(candidate.id, tender_id)
                audit.append(
                    actor=actor,
                    action="tender.scan_candidate_confirm",
                    object_type="steven_tender_job",
                    object_id=tender_id,
                    request_id=request_id,
                    before_after={
                        "before": {"candidate_status": "needs_review"},
                        "after": {
                            "candidate_id": candidate.id,
                            "candidate_status": "confirmed",
                            "updated_fields": sorted(update_values),
                            "draft_status": preview.tender.status,
                        },
                    },
                )
                return {
                    "candidate": candidate.model_dump(mode="json"),
                    "tender": preview.tender.model_dump(mode="json"),
                    "valid": preview.valid,
                    "unresolved_variables": preview.unresolved_variables,
                }
        except ValidationError as error:
            raise ApiError(422, "candidate_revision_invalid", "人工修订字段未通过文书规则校验。", {"fields": [item["loc"] for item in error.errors()]}) from error
        except IntegrityError as error:
            raise ApiError(409, "candidate_write_conflict", "候选确认与其他写入冲突，已回滚，请刷新后重试。") from error
