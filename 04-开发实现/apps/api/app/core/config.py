from __future__ import annotations

import os
from dataclasses import dataclass
import ipaddress
from typing import Literal

AppEnv = Literal["development", "test", "staging", "production"]
AuthMode = Literal["mock", "session", "sso"]
RateLimitMode = Literal["memory", "redis", "gateway"]
OcrProvider = Literal["mock", "paddle", "azure_document_intelligence"]
AiStructuringProvider = Literal["mock", "deepseek"]


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _csv_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = os.getenv(name)
    if value is None:
        return default
    return tuple(item.strip().rstrip("/") for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    app_env: AppEnv = "development"
    auth_mode: AuthMode = "mock"
    demo_seed_enabled: bool = True
    database_url: str = ""
    file_storage_root: str = "./data/development"
    mock_identity: str = "steven"
    session_idle_minutes: int = 30
    session_absolute_hours: int = 8
    session_cookie_name: str = "__Host-puiying_session"
    session_cookie_secure: bool = True
    csrf_cookie_name: str = "__Host-puiying_csrf"
    csrf_header_name: str = "X-CSRF-Token"
    allowed_origins: tuple[str, ...] = ("https://testserver",)
    login_max_failures: int = 5
    login_lock_minutes: int = 15
    login_rate_limit_attempts: int = 10
    login_rate_limit_window_seconds: int = 300
    rate_limit_mode: str = "memory"
    redis_rate_limit_url: str = ""
    trusted_proxy_cidrs: tuple[str, ...] = ()
    demo_profile_enabled: bool = True
    ocr_enabled: bool = True
    ocr_provider: OcrProvider = "paddle"
    ocr_endpoint: str = ""
    ocr_model: str = "prebuilt-invoice"
    ocr_timeout_seconds: int = 30
    ai_structuring_enabled: bool = True
    ai_structuring_provider: AiStructuringProvider = "mock"
    ai_structuring_endpoint: str = ""
    ai_structuring_model: str = "deepseek-chat"
    ai_structuring_timeout_seconds: int = 30

    @classmethod
    def from_env(cls) -> "Settings":
        app_env = os.getenv("APP_ENV", "development").strip().lower()
        return cls(
            app_env=app_env,  # type: ignore[arg-type]
            auth_mode=os.getenv("AUTH_MODE", "mock").strip().lower(),  # type: ignore[arg-type]
            demo_seed_enabled=_bool_env("DEMO_SEED_ENABLED", app_env in {"development", "test"}),
            database_url=os.getenv("DATABASE_URL", "").strip(),
            file_storage_root=os.getenv("FILE_STORAGE_ROOT", f"./data/{app_env}").strip(),
            mock_identity=os.getenv("MOCK_IDENTITY", "steven").strip().lower(),
            session_idle_minutes=int(os.getenv("SESSION_IDLE_MINUTES", "30")),
            session_absolute_hours=int(os.getenv("SESSION_ABSOLUTE_HOURS", "8")),
            session_cookie_name=os.getenv("SESSION_COOKIE_NAME", "__Host-puiying_session").strip(),
            session_cookie_secure=_bool_env("SESSION_COOKIE_SECURE", True),
            csrf_cookie_name=os.getenv("CSRF_COOKIE_NAME", "__Host-puiying_csrf").strip(),
            csrf_header_name=os.getenv("CSRF_HEADER_NAME", "X-CSRF-Token").strip(),
            allowed_origins=_csv_env(
                "ALLOWED_ORIGINS",
                ("http://127.0.0.1:3000", "http://localhost:3000") if app_env == "development" else ("https://testserver",) if app_env == "test" else (),
            ),
            login_max_failures=int(os.getenv("LOGIN_MAX_FAILURES", "5")),
            login_lock_minutes=int(os.getenv("LOGIN_LOCK_MINUTES", "15")),
            login_rate_limit_attempts=int(os.getenv("LOGIN_RATE_LIMIT_ATTEMPTS", "10")),
            login_rate_limit_window_seconds=int(os.getenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "300")),
            rate_limit_mode=os.getenv("RATE_LIMIT_MODE", "memory" if app_env in {"development", "test"} else "").strip().lower(),
            redis_rate_limit_url=os.getenv("REDIS_RATE_LIMIT_URL", "").strip(),
            trusted_proxy_cidrs=_csv_env("TRUSTED_PROXY_CIDRS", ()),
            demo_profile_enabled=_bool_env("DEMO_PROFILE_ENABLED", app_env in {"development", "test"}),
            ocr_enabled=_bool_env("OCR_ENABLED", True),
            ocr_provider=os.getenv("OCR_PROVIDER", "paddle").strip().lower(),  # type: ignore[arg-type]
            ocr_endpoint=os.getenv("OCR_ENDPOINT", "").strip(),
            ocr_model=os.getenv("OCR_MODEL", "prebuilt-invoice").strip(),
            ocr_timeout_seconds=int(os.getenv("OCR_TIMEOUT_SECONDS", "30")),
            ai_structuring_enabled=_bool_env("AI_STRUCTURING_ENABLED", True),
            ai_structuring_provider=os.getenv("AI_STRUCTURING_PROVIDER", "mock").strip().lower(),  # type: ignore[arg-type]
            ai_structuring_endpoint=os.getenv("AI_STRUCTURING_ENDPOINT", "").strip(),
            ai_structuring_model=os.getenv("AI_STRUCTURING_MODEL", "deepseek-chat").strip(),
            ai_structuring_timeout_seconds=int(os.getenv("AI_STRUCTURING_TIMEOUT_SECONDS", "30")),
        )

    def validate(self) -> None:
        if self.app_env not in {"development", "test", "staging", "production"}:
            raise RuntimeError(f"Unsupported APP_ENV: {self.app_env}")
        if self.auth_mode not in {"mock", "session", "sso"}:
            raise RuntimeError(f"Unsupported AUTH_MODE: {self.auth_mode}")
        if self.auth_mode == "mock" and self.app_env not in {"development", "test"}:
            raise RuntimeError("AUTH_MODE=mock is forbidden outside development/test")
        if self.app_env == "production" and self.demo_seed_enabled:
            raise RuntimeError("DEMO_SEED_ENABLED=true is forbidden in production")
        if self.app_env in {"staging", "production"} and self.auth_mode == "session" and self.demo_seed_enabled:
            raise RuntimeError("DEMO_SEED_ENABLED=true is forbidden in staging/production session mode")
        if self.session_idle_minutes <= 0 or self.session_absolute_hours <= 0:
            raise RuntimeError("Session timeouts must be positive")
        if self.login_max_failures <= 0 or self.login_lock_minutes <= 0:
            raise RuntimeError("Login lockout settings must be positive")
        if self.login_rate_limit_attempts <= 0 or self.login_rate_limit_window_seconds <= 0:
            raise RuntimeError("Login rate-limit settings must be positive")
        if self.rate_limit_mode not in {"memory", "redis", "gateway"}:
            raise RuntimeError("RATE_LIMIT_MODE must be memory, redis, or gateway")
        if self.app_env in {"staging", "production"} and self.rate_limit_mode == "memory":
            raise RuntimeError("RATE_LIMIT_MODE must use redis or gateway in staging/production")
        if self.rate_limit_mode == "redis" and not self.redis_rate_limit_url:
            raise RuntimeError("REDIS_RATE_LIMIT_URL is required when RATE_LIMIT_MODE=redis")
        try:
            for cidr in self.trusted_proxy_cidrs:
                ipaddress.ip_network(cidr, strict=False)
        except ValueError as error:
            raise RuntimeError("TRUSTED_PROXY_CIDRS contains an invalid network") from error
        if self.app_env in {"staging", "production"} and self.rate_limit_mode == "gateway" and not self.trusted_proxy_cidrs:
            raise RuntimeError("TRUSTED_PROXY_CIDRS is required when RATE_LIMIT_MODE=gateway")
        if self.app_env in {"staging", "production"} and not self.session_cookie_secure:
            raise RuntimeError("Secure session cookies are required in staging/production")
        if self.auth_mode == "session" and not self.allowed_origins:
            raise RuntimeError("ALLOWED_ORIGINS is required for session auth")
        if self.app_env in {"staging", "production"} and any(not origin.startswith("https://") for origin in self.allowed_origins):
            raise RuntimeError("Only HTTPS ALLOWED_ORIGINS are permitted in staging/production")
        if self.auth_mode == "sso":
            raise RuntimeError("AUTH_MODE=sso is reserved until a school SSO adapter is configured")
        if self.auth_mode == "session" and self.app_env in {"staging", "production"}:
            if not self.database_url or any(marker in self.database_url for marker in {"<", ">", "change-me"}):
                raise RuntimeError("A non-placeholder DATABASE_URL is required for session auth")
            if not self.file_storage_root or any(marker in self.file_storage_root for marker in {"<", ">", "change-me"}):
                raise RuntimeError("A non-placeholder FILE_STORAGE_ROOT is required for session auth")
        if self.ocr_provider not in {"mock", "paddle", "azure_document_intelligence"}:
            raise RuntimeError("OCR_PROVIDER must be mock, paddle, or azure_document_intelligence")
        if self.ai_structuring_provider not in {"mock", "deepseek"}:
            raise RuntimeError("AI_STRUCTURING_PROVIDER must be mock or deepseek")
        if self.ocr_timeout_seconds <= 0 or self.ai_structuring_timeout_seconds <= 0:
            raise RuntimeError("OCR/AI timeouts must be positive")
        if (self.ocr_enabled or self.ai_structuring_enabled) and not self.demo_profile_enabled:
            raise RuntimeError("OCR/AI may only be enabled under the controlled demo profile")
        if self.ocr_enabled and self.ocr_provider == "azure_document_intelligence" and not self.ocr_endpoint:
            raise RuntimeError("OCR_ENDPOINT is required for Azure Document Intelligence")
        if self.ai_structuring_enabled and self.ai_structuring_provider == "deepseek" and not self.ai_structuring_endpoint:
            raise RuntimeError("AI_STRUCTURING_ENDPOINT is required for DeepSeek")
