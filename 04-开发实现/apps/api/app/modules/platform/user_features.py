from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, text

from app.core.api_response import ApiError
from app.core.audit import PostgresAuditRepository
from app.core.passwords import hash_password, verify_password


class UserFeaturesService:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get_settings(self, user_id: str) -> dict[str, Any]:
        with self._engine.connect() as connection:
            row = connection.execute(
                text("""
                    SELECT u.id,u.username,u.display_name,coalesce(p.locale,'zh-TW') AS locale
                    FROM users u LEFT JOIN user_preferences p ON p.user_id=u.id
                    WHERE u.id=:user_id AND u.status='active'
                """),
                {"user_id": user_id},
            ).mappings().first()
        if row is None:
            raise ApiError(404, "user_not_found", "找不到使用者。")
        return dict(row)

    def update_settings(self, user_id: str, display_name: str, locale: str, request_id: str) -> dict[str, Any]:
        normalized_name = display_name.strip()
        if not normalized_name:
            raise ApiError(422, "display_name_required", "顯示名稱不可留空。")
        if locale not in {"zh-TW", "zh-CN"}:
            raise ApiError(422, "unsupported_locale", "不支援的語言設定。")
        with self._engine.begin() as connection:
            before = connection.execute(text("SELECT display_name FROM users WHERE id=:id FOR UPDATE"), {"id": user_id}).mappings().first()
            if before is None:
                raise ApiError(404, "user_not_found", "找不到使用者。")
            connection.execute(text("UPDATE users SET display_name=:display_name, updated_at=now() WHERE id=:id"), {"display_name": normalized_name, "id": user_id})
            connection.execute(
                text("""
                    INSERT INTO user_preferences (user_id,locale,created_at,updated_at)
                    VALUES (:user_id,:locale,now(),now())
                    ON CONFLICT (user_id) DO UPDATE SET locale=excluded.locale,updated_at=now()
                """),
                {"user_id": user_id, "locale": locale},
            )
            PostgresAuditRepository(connection).append(
                actor=user_id,
                action="profile.update",
                object_type="user_profile",
                object_id=user_id,
                request_id=request_id,
                before_after={"before": {"display_name": before["display_name"]}, "after": {"display_name": normalized_name, "locale": locale}},
            )
        return self.get_settings(user_id)

    def change_password(self, user_id: str, session_id: str | None, old_password: str, new_password: str, request_id: str) -> None:
        if len(new_password) < 6:
            raise ApiError(422, "password_too_short", "新密碼至少需要 6 個字元。")
        with self._engine.begin() as connection:
            row = connection.execute(text("SELECT password_hash FROM users WHERE id=:id FOR UPDATE"), {"id": user_id}).mappings().first()
            if row is None or not verify_password(old_password, row["password_hash"]):
                raise ApiError(400, "old_password_invalid", "舊密碼不正確。")
            if verify_password(new_password, row["password_hash"]):
                raise ApiError(422, "password_unchanged", "新密碼不可與舊密碼相同。")
            connection.execute(text("UPDATE users SET password_hash=:password_hash, updated_at=now() WHERE id=:id"), {"password_hash": hash_password(new_password), "id": user_id})
            if session_id is None:
                connection.execute(
                    text("UPDATE auth_sessions SET revoked_at=now(),revoke_reason='password_changed' WHERE user_id=:user_id AND revoked_at IS NULL"),
                    {"user_id": user_id},
                )
            else:
                connection.execute(
                    text("UPDATE auth_sessions SET revoked_at=now(),revoke_reason='password_changed' WHERE user_id=:user_id AND revoked_at IS NULL AND id<>:session_id"),
                    {"user_id": user_id, "session_id": session_id},
                )
            PostgresAuditRepository(connection).append(
                actor=user_id,
                action="auth.password_changed",
                object_type="user_account",
                object_id=user_id,
                request_id=request_id,
                before_after={"before": None, "after": {"other_sessions_revoked": True}},
            )

    def list_notifications(self, user_id: str, unread_only: bool = False, limit: int = 100) -> list[dict[str, Any]]:
        clause = "AND n.read_at IS NULL" if unread_only else ""
        with self._engine.connect() as connection:
            rows = connection.execute(
                text(f"""
                    SELECT n.id,n.module,n.event_type,n.object_type,n.object_id,n.target_path,n.payload_json,
                           n.request_id,n.read_at,n.created_at,u.display_name AS actor_display_name
                    FROM user_notifications n LEFT JOIN users u ON u.id=n.actor_user_id
                    WHERE n.recipient_user_id=:user_id {clause}
                    ORDER BY n.created_at DESC,n.id DESC LIMIT :limit
                """),
                {"user_id": user_id, "limit": min(max(limit, 1), 200)},
            ).mappings().all()
        return [self._serialize(row) for row in rows]

    def unread_count(self, user_id: str) -> int:
        with self._engine.connect() as connection:
            return int(connection.execute(text("SELECT count(*) FROM user_notifications WHERE recipient_user_id=:id AND read_at IS NULL"), {"id": user_id}).scalar_one())

    def mark_notification_read(self, user_id: str, notification_id: str) -> bool:
        with self._engine.begin() as connection:
            result = connection.execute(text("UPDATE user_notifications SET read_at=coalesce(read_at,now()) WHERE id=:id AND recipient_user_id=:user_id"), {"id": notification_id, "user_id": user_id})
        return result.rowcount > 0

    def mark_all_read(self, user_id: str) -> int:
        with self._engine.begin() as connection:
            result = connection.execute(text("UPDATE user_notifications SET read_at=now() WHERE recipient_user_id=:user_id AND read_at IS NULL"), {"user_id": user_id})
        return result.rowcount

    def history(self, module: str | None, limit: int = 100) -> list[dict[str, Any]]:
        bounded_limit = min(max(limit, 1), 200)
        include_platform = module in {None, "s1", "s3"}
        include_quotes = module in {None, "s2"}
        platform_pattern = {"s1": "tender.%", "s3": "inventory.%"}.get(module or "")
        statements: list[str] = []
        parameters: dict[str, Any] = {"limit": bounded_limit}
        if include_platform:
            platform_where = "action LIKE :platform_pattern" if platform_pattern else "action LIKE 'tender.%' OR action LIKE 'inventory.%'"
            if platform_pattern:
                parameters["platform_pattern"] = platform_pattern
            statements.append(f"""
                SELECT e.id,e.actor_user_id,e.actor_label,e.action,e.outcome,e.object_type,e.object_id,
                       e.request_id,e.occurred_at,e.before_after,u.display_name AS actor_display_name
                FROM platform_audit_events e LEFT JOIN users u ON u.id=e.actor_user_id
                WHERE {platform_where}
            """)
        if include_quotes:
            statements.append("""
                SELECT e.id,e.actor_user_id,NULL::varchar AS actor_label,e.action,'success'::varchar AS outcome,
                       e.object_type,e.object_id,e.request_id,e.occurred_at,e.before_after,
                       u.display_name AS actor_display_name
                FROM steven_quote_audit_events e LEFT JOIN users u ON u.id=e.actor_user_id
            """)
        with self._engine.connect() as connection:
            rows = connection.execute(
                text(f"SELECT * FROM ({' UNION ALL '.join(statements)}) AS history ORDER BY occurred_at DESC,id DESC LIMIT :limit"),
                parameters,
            ).mappings().all()
        return [self._serialize(row) for row in rows]

    @staticmethod
    def _serialize(row: Any) -> dict[str, Any]:
        data = dict(row)
        for key in ("created_at", "read_at", "occurred_at"):
            if data.get(key) is not None:
                data[key] = data[key].isoformat()
        return data