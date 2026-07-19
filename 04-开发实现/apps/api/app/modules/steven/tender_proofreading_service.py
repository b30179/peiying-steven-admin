from __future__ import annotations

import hashlib
import json
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import Engine, text

from app.core.api_response import ApiError
from app.core.audit import PostgresAuditRepository
from app.modules.document_intelligence.adapters import AiStructuringAdapter
from app.modules.document_intelligence.schemas import AiStructuringRequest, EvidenceLocation
from app.modules.steven.tender_service import find_unresolved_placeholders

ReviewDecision = Literal["accepted", "ignored"]


def apply_proofreading_replacement(rendered_body: str, original_text: str, replacement_text: str) -> str:
    if not original_text:
        raise ApiError(422, "proofreading_original_empty", "AI 校對原文為空，不能自動套用；請使用人工修訂。")
    if original_text == replacement_text:
        return rendered_body
    occurrences = rendered_body.count(original_text)
    if occurrences == 0:
        raise ApiError(409, "proofreading_original_not_found", "目前草稿已找不到該段 AI 原文；請重新校對或使用人工修訂。")
    if occurrences > 1:
        raise ApiError(409, "proofreading_original_ambiguous", "該段原文在目前草稿中出現多次，為避免誤改，請使用人工修訂。")
    return rendered_body.replace(original_text, replacement_text, 1)


class TenderProofreadingService:
    def __init__(self, engine: Engine, adapter: AiStructuringAdapter | None, *, enabled: bool, provider: str, model: str) -> None:
        self._engine = engine
        self._adapter = adapter
        self._enabled = enabled
        self._provider = provider
        self._model = model

    def start(self, tender_id: str, actor_id: str, request_id: str) -> dict[str, Any]:
        if not self._enabled:
            raise ApiError(409, "ai_structuring_disabled", "AI 校對目前已關閉；請繼續人工校對。")
        if self._adapter is None:
            raise ApiError(503, "ai_provider_unavailable", "AI 校對服務尚未完成設定。")
        with self._engine.begin() as connection:
            tender = connection.execute(
                text("SELECT id,rendered_body,is_demo FROM steven_tender_jobs WHERE id=:id FOR UPDATE"),
                {"id": tender_id},
            ).mappings().first()
            if tender is None:
                raise ApiError(404, "tender_not_found", "找不到文書事項。")
            if self._provider == "deepseek" and not tender["is_demo"]:
                raise ApiError(409, "ai_requires_redacted_demo", "DeepSeek 校對只允許傳送已標記的脫敏 Demo 文書。")
            body = (tender["rendered_body"] or "").strip()
            if not body:
                raise ApiError(409, "tender_draft_required", "請先生成草稿，再執行 AI 校對。")
            encoded = body.encode("utf-8")
            digest = hashlib.sha256(encoded).hexdigest()
            file_id = str(uuid4())
            ai_job_id = str(uuid4())
            connection.execute(
                text("""
                    INSERT INTO files (id,module,document_type,purpose,original_filename,storage_key,mime_type,size_bytes,sha256,status,is_demo,created_by,request_id,created_at)
                    VALUES (:id,'steven','tender_document','tender_proofreading',:filename,:storage_key,'text/plain',:size_bytes,:sha256,'stored',:is_demo,:actor,:request_id,now())
                """),
                {"id": file_id, "filename": f"{tender_id}-draft.txt", "storage_key": f"virtual://tender-proofreading/{tender_id}/{digest}/{file_id}", "size_bytes": len(encoded), "sha256": digest, "is_demo": tender["is_demo"], "actor": actor_id, "request_id": request_id},
            )
            connection.execute(
                text("""
                    INSERT INTO ai_jobs (id,file_id,module,document_type,purpose,provider,model,status,request_id,output_json,created_at,updated_at)
                    VALUES (:id,:file_id,'steven','tender_document','tender_proofreading',:provider,:model,'running',:request_id,'{}'::jsonb,now(),now())
                """),
                {"id": ai_job_id, "file_id": file_id, "provider": self._provider, "model": self._model, "request_id": request_id},
            )
        try:
            result = self._adapter.structure(AiStructuringRequest(
                document_type="tender_document",
                purpose="tender_proofreading",
                schema_name="steven.s1.tender_proofreading",
                schema_version="1.0",
                request_id=request_id,
                sanitized_text=f"DOCUMENT_SHA256:{digest}\nDOCUMENT_CONTENT:\n{body}",
                evidence=[EvidenceLocation(field_path="rendered_body", page=1, original_text=body[:4000] or "empty", bbox=[0, 0, 1, 1], confidence=1)],
            ))
            if result.candidate.get("document_sha256") != digest:
                raise ValueError("proofreading_document_hash_mismatch")
        except Exception:
            with self._engine.begin() as connection:
                connection.execute(text("UPDATE ai_jobs SET status='failed',error_code='provider_failed',updated_at=now() WHERE id=:id"), {"id": ai_job_id})
                PostgresAuditRepository(connection).append(actor=actor_id, action="tender.proofreading_failed", object_type="steven_tender_job", object_id=tender_id, request_id=request_id, before_after={"before": None, "after": {"ai_job_id": ai_job_id, "status": "failed"}})
            raise ApiError(502, "ai_proofreading_failed", "AI 校對失敗或逾時，未建立成功候選；請稍後重試或改用人工校對。")

        candidate_id = str(uuid4())
        with self._engine.begin() as connection:
            values = {"output": json.dumps(result.candidate, ensure_ascii=False), "id": ai_job_id, "candidate_id": candidate_id, "file_id": file_id, "ai_job_id": ai_job_id, "provider": result.provider, "model": result.model, "candidate": json.dumps(result.candidate, ensure_ascii=False), "warnings": json.dumps(result.warnings, ensure_ascii=False), "evidence": "[]", "tender_id": tender_id, "request_id": request_id, "sha256": digest}
            connection.execute(text("UPDATE ai_jobs SET status='needs_review',output_json=CAST(:output AS jsonb),updated_at=now() WHERE id=:id"), values)
            connection.execute(
                text("""
                    INSERT INTO review_candidates (
                        id,source_file_id,ai_job_id,module,document_type,purpose,schema_name,schema_version,provider,model,status,
                        candidate_json,human_revision_json,warnings,evidence,reviewer_id,target_object_type,target_object_id,request_id,created_at,updated_at
                    ) VALUES (
                        :candidate_id,:file_id,:ai_job_id,'steven','tender_document','tender_proofreading','steven.s1.tender_proofreading','1.0',
                        :provider,:model,'needs_review',CAST(:candidate AS jsonb),NULL,CAST(:warnings AS jsonb),CAST(:evidence AS jsonb),NULL,
                        'steven_tender_job',:tender_id,:request_id,now(),now()
                    )
                """),
                values,
            )
            connection.execute(text("INSERT INTO steven_tender_review_candidates (candidate_id,tender_job_id,draft_sha256,created_at) VALUES (:candidate_id,:tender_id,:sha256,now())"), values)
            connection.execute(text("INSERT INTO steven_tender_candidate_links (candidate_id,tender_job_id,candidate_kind,created_at) VALUES (:candidate_id,:tender_id,'tender_proofreading',now())"), values)
            PostgresAuditRepository(connection).append(actor=actor_id, action="tender.proofreading_requested", object_type="steven_tender_job", object_id=tender_id, request_id=request_id, before_after={"before": None, "after": {"ai_job_id": ai_job_id, "candidate_id": candidate_id, "status": "needs_review", "source": result.source}})
        return self.get(tender_id, candidate_id)

    def list(self, tender_id: str) -> list[dict[str, Any]]:
        with self._engine.connect() as connection:
            rows = connection.execute(text("""
                SELECT r.*,l.draft_sha256 FROM review_candidates r
                JOIN steven_tender_review_candidates l ON l.candidate_id=r.id
                WHERE l.tender_job_id=:tender_id ORDER BY r.created_at DESC,r.id DESC
            """), {"tender_id": tender_id}).mappings().all()
        return [self._view(row) for row in rows]

    def get(self, tender_id: str, candidate_id: str) -> dict[str, Any]:
        with self._engine.connect() as connection:
            row = connection.execute(text("""
                SELECT r.*,l.draft_sha256 FROM review_candidates r
                JOIN steven_tender_review_candidates l ON l.candidate_id=r.id
                WHERE l.tender_job_id=:tender_id AND r.id=:candidate_id
            """), {"tender_id": tender_id, "candidate_id": candidate_id}).mappings().first()
        if row is None:
            raise ApiError(404, "proofreading_candidate_not_found", "找不到 AI 校對候選。")
        return self._view(row)

    def review(self, tender_id: str, candidate_id: str, decisions: dict[str, ReviewDecision], actor_id: str, request_id: str) -> dict[str, Any]:
        current = self.get(tender_id, candidate_id)
        if current["status"] != "needs_review":
            raise ApiError(409, "candidate_not_reviewable", "此候選已完成處理。")
        issue_ids = {issue["issue_id"] for issue in current["candidate_json"].get("issues", [])}
        if not set(decisions).issubset(issue_ids) or any(value not in {"accepted", "ignored"} for value in decisions.values()):
            raise ApiError(422, "invalid_review_decision", "覆核決定包含未知問題或無效狀態。")
        revision = dict(current.get("human_revision_json") or {})
        existing_decisions = dict(revision.get("decisions") or {})
        applied_issue_ids = set((revision.get("applied_replacements") or {}).keys())
        if any(decisions.get(issue_id) != "accepted" for issue_id in applied_issue_ids):
            raise ApiError(409, "applied_decision_immutable", "已套用到草稿的 AI 建議不可改為忽略；如需調整請使用人工修訂。")
        revision["decisions"] = decisions
        with self._engine.begin() as connection:
            connection.execute(text("UPDATE review_candidates SET human_revision_json=CAST(:revision AS jsonb),reviewer_id=:actor,updated_at=now() WHERE id=:id AND status='needs_review'"), {"revision": json.dumps(revision, ensure_ascii=False), "actor": actor_id, "id": candidate_id})
            PostgresAuditRepository(connection).append(actor=actor_id, action="tender.proofreading_reviewed", object_type="review_candidate", object_id=candidate_id, request_id=request_id, before_after={"before": {"decision_count": len(existing_decisions)}, "after": {"decision_count": len(decisions)}})
        return self.get(tender_id, candidate_id)

    def apply_issue(
        self,
        tender_id: str,
        candidate_id: str,
        issue_id: str,
        replacement_text: str,
        actor_id: str,
        request_id: str,
    ) -> dict[str, Any]:
        with self._engine.begin() as connection:
            row = connection.execute(text("""
                SELECT r.status AS candidate_status,r.candidate_json,r.human_revision_json,l.draft_sha256,
                       t.rendered_body,t.status AS tender_status
                  FROM review_candidates r
                  JOIN steven_tender_review_candidates l ON l.candidate_id=r.id
                  JOIN steven_tender_jobs t ON t.id=l.tender_job_id
                 WHERE l.tender_job_id=:tender_id AND r.id=:candidate_id
                 FOR UPDATE OF r,t
            """), {"tender_id": tender_id, "candidate_id": candidate_id}).mappings().first()
            if row is None:
                raise ApiError(404, "proofreading_candidate_not_found", "找不到 AI 校對候選。")
            if row["candidate_status"] != "needs_review":
                raise ApiError(409, "candidate_not_reviewable", "此候選已完成處理。")
            if row["tender_status"] not in {"draft", "draft_error", "returned"}:
                raise ApiError(409, "tender_not_editable", "目前文書狀態不可套用 AI 建議。", {"status": row["tender_status"]})

            issues = row["candidate_json"].get("issues", [])
            issue = next((item for item in issues if item.get("issue_id") == issue_id), None)
            if issue is None:
                raise ApiError(404, "proofreading_issue_not_found", "找不到指定的 AI 校對問題。")

            revision = dict(row["human_revision_json"] or {})
            decisions = dict(revision.get("decisions") or {})
            applied_replacements = dict(revision.get("applied_replacements") or {})
            if issue_id in applied_replacements:
                raise ApiError(409, "proofreading_issue_already_applied", "此 AI 建議已套用到草稿。")

            rendered_body = row["rendered_body"] or ""
            current_digest = hashlib.sha256(rendered_body.encode("utf-8")).hexdigest()
            expected_digest = revision.get("current_draft_sha256") or row["draft_sha256"]
            if current_digest != expected_digest:
                raise ApiError(409, "proofreading_candidate_stale", "草稿已在校對後變更；請重新執行 AI 校對，避免套用過期建議。")

            updated_body = apply_proofreading_replacement(rendered_body, issue.get("original_text", ""), replacement_text)
            updated_digest = hashlib.sha256(updated_body.encode("utf-8")).hexdigest()
            unresolved = find_unresolved_placeholders(updated_body)
            updated_status = "draft_error" if unresolved else "draft"
            connection.execute(text("""
                UPDATE steven_tender_jobs
                   SET rendered_body=:rendered_body,
                       unresolved_variables=CAST(:unresolved AS jsonb),
                       status=:status,
                       submitted_by=NULL,submitted_at=NULL,decided_by=NULL,decided_at=NULL,decision_opinion=NULL,
                       updated_by=:actor,updated_at=now()
                 WHERE id=:tender_id
            """), {
                "rendered_body": updated_body,
                "unresolved": json.dumps(unresolved, ensure_ascii=False),
                "status": updated_status,
                "actor": actor_id,
                "tender_id": tender_id,
            })
            decisions[issue_id] = "accepted"
            applied_replacements[issue_id] = {
                "original_text": issue.get("original_text", ""),
                "replacement_text": replacement_text,
                "draft_sha256": updated_digest,
            }
            revision.update({
                "decisions": decisions,
                "applied_replacements": applied_replacements,
                "current_draft_sha256": updated_digest,
            })
            connection.execute(text("""
                UPDATE review_candidates
                   SET human_revision_json=CAST(:revision AS jsonb),reviewer_id=:actor,updated_at=now()
                 WHERE id=:candidate_id AND status='needs_review'
            """), {
                "revision": json.dumps(revision, ensure_ascii=False),
                "actor": actor_id,
                "candidate_id": candidate_id,
            })
            PostgresAuditRepository(connection).append(
                actor=actor_id,
                action="tender.proofreading_issue_applied",
                object_type="steven_tender_job",
                object_id=tender_id,
                request_id=request_id,
                before_after={
                    "before": {"candidate_id": candidate_id, "issue_id": issue_id, "draft_sha256": current_digest},
                    "after": {"candidate_id": candidate_id, "issue_id": issue_id, "draft_sha256": updated_digest, "status": updated_status, "unresolved_count": len(unresolved)},
                },
            )
        return self.get(tender_id, candidate_id)

    def confirm(self, tender_id: str, candidate_id: str, actor_id: str, request_id: str) -> dict[str, Any]:
        current = self.get(tender_id, candidate_id)
        issues = current["candidate_json"].get("issues", [])
        decisions = (current.get("human_revision_json") or {}).get("decisions", {})
        if {issue["issue_id"] for issue in issues} != set(decisions):
            raise ApiError(409, "proofreading_review_incomplete", "請逐條接受或忽略所有問題後再確認。")
        with self._engine.begin() as connection:
            result = connection.execute(text("UPDATE review_candidates SET status='confirmed',reviewer_id=:actor,reviewed_at=now(),updated_at=now() WHERE id=:id AND status='needs_review'"), {"actor": actor_id, "id": candidate_id})
            if result.rowcount != 1:
                raise ApiError(409, "candidate_not_reviewable", "此候選已完成處理。")
            connection.execute(text("UPDATE ai_jobs SET status='confirmed',updated_at=now() WHERE id=(SELECT ai_job_id FROM review_candidates WHERE id=:id)"), {"id": candidate_id})
            PostgresAuditRepository(connection).append(actor=actor_id, action="tender.proofreading_confirmed", object_type="review_candidate", object_id=candidate_id, request_id=request_id, before_after={"before": {"status": "needs_review"}, "after": {"status": "confirmed", "decision_count": len(decisions)}})
        return self.get(tender_id, candidate_id)

    @staticmethod
    def _view(row: Any) -> dict[str, Any]:
        data = dict(row)
        for key in ("created_at", "updated_at", "reviewed_at"):
            if data.get(key) is not None:
                data[key] = data[key].isoformat()
        return data