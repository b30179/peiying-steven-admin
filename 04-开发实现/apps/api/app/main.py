from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy import Engine
from sqlalchemy.engine import make_url

from app.core.api_response import ApiError, error_response, request_id_middleware, success
from app.core.config import Settings
from app.core.login_protection import GatewayLoginRateLimiter, LoginRateLimiter, MemoryLoginRateLimiter
from app.core.request_security import request_security_middleware
from app.db.session import create_postgres_engine
from app.modules.accounts.repository import AuthRepository, InMemoryAuthRepository, PostgresAuthRepository
from app.modules.accounts.router import admin_router, auth_router
from app.core.audit import AuditRepository, PlatformAuditRepository, PostgresAuditRepository, development_audit_repository
from app.modules.document_intelligence.adapters import MockAiStructuringAdapter, MockOcrAdapter
from app.modules.document_intelligence.paddle_ocr_adapter import PaddleOcrAdapter
from app.modules.document_intelligence.postgres_service import PostgresDocumentIntelligenceService
from app.modules.document_intelligence.repository import InMemoryDocumentIntelligenceRepository
from app.modules.document_intelligence.router import documents_router, router as document_intelligence_router
from app.modules.document_intelligence.routing_adapter import DisabledAiStructuringAdapter, DisabledOcrAdapter, RoutingAiStructuringAdapter
from app.modules.document_intelligence.service import DocumentIntelligenceService
from app.modules.document_intelligence.storage import InMemoryDocumentFileStorage, LocalAppendOnlyDocumentFileStorage
from app.modules.document_intelligence.tender_source_adapter import TenderSourceRuleAdapter
from app.modules.steven.scan_import_application import InMemoryScanImportUnitOfWork, PostgresScanImportUnitOfWork, StevenScanImportApplicationService
from app.modules.steven.ai_adapter import (
    DeepSeekStructuringAdapter,
    MockTenderProofreadingAdapter,
    httpx_json_transport,
)
from app.modules.steven.ai_assist_service import StevenAiAssistService
from app.modules.platform.append_only_storage import LocalAppendOnlyFileStorage
from app.modules.platform.user_features import UserFeaturesService
from app.modules.platform.user_features_router import router as user_features_router
from app.modules.steven.quote_application import StevenQuoteApplicationService
from app.modules.steven.quote_excel import LocalAppendOnlyQuoteStorage, QuoteExcelExporter, QuoteImportParser
from app.modules.steven.quote_repository import StevenQuoteRepository
from app.modules.steven.quote_uow import InMemoryQuoteUnitOfWork, PostgresQuoteUnitOfWork
from app.modules.steven.quotes_router import quotes_router
from app.modules.steven.router import audit_router, router as steven_router
from app.modules.steven.inventory_application import StevenInventoryApplicationService
from app.modules.steven.inventory_excel import InventoryExcelRenderer
from app.modules.steven.inventory_import import InventoryImportParser
from app.modules.steven.inventory_repository import InMemoryInventoryRepository
from app.modules.steven.inventory_router import inventory_router
from app.modules.steven.inventory_uow import InMemoryInventoryUnitOfWork, PostgresInventoryUnitOfWork
from app.modules.steven.tender_application import StevenTenderApplicationService
from app.modules.steven.tender_repository import InMemoryTenderRepository
from app.modules.steven.tender_uow import InMemoryTenderUnitOfWork, PostgresTenderUnitOfWork
from app.modules.steven.tender_word import TenderWordRenderer
from app.modules.steven.tender_proofreading_service import TenderProofreadingService
from app.modules.steven.tender_scan_application import TenderScanApplicationService
from app.modules.steven.tenders_router import tenders_router


class LazyPostgresQuoteApplication:
    def __init__(self, settings: Settings, engine: Engine | None = None) -> None:
        self._settings = settings
        self._engine = engine
        self._application = None

    def _resolve(self):
        if self._application is None:
            engine = self._engine or create_postgres_engine(self._settings)
            exporter = QuoteExcelExporter(Path(self._settings.file_storage_root))
            storage = LocalAppendOnlyQuoteStorage(exporter.data_root)
            self._application = StevenQuoteApplicationService(PostgresQuoteUnitOfWork(engine), QuoteImportParser(), exporter, storage)
        return self._application

    def __getattr__(self, name):
        return getattr(self._resolve(), name)


class LazyPostgresTenderApplication:
    def __init__(self, settings: Settings, engine: Engine | None = None) -> None:
        self._settings = settings
        self._engine = engine
        self._application = None

    def _resolve(self):
        if self._application is None:
            engine = self._engine or create_postgres_engine(self._settings)
            renderer = TenderWordRenderer()
            storage = LocalAppendOnlyFileStorage(
                Path(self._settings.file_storage_root),
                "tenders",
                "docx",
                renderer.verify,
            )
            self._application = StevenTenderApplicationService(
                PostgresTenderUnitOfWork(engine),
                renderer,
                storage,
            )
        return self._application

    def __getattr__(self, name):
        return getattr(self._resolve(), name)


class LazyPostgresInventoryApplication:
    def __init__(self, settings: Settings, engine: Engine | None = None) -> None:
        self._settings = settings
        self._engine = engine
        self._application = None

    def _resolve(self):
        if self._application is None:
            engine = self._engine or create_postgres_engine(self._settings)
            renderer = InventoryExcelRenderer()
            storage = LocalAppendOnlyFileStorage(
                Path(self._settings.file_storage_root),
                "inventory",
                "xlsx",
                renderer.verify,
            )
            self._application = StevenInventoryApplicationService(
                PostgresInventoryUnitOfWork(engine),
                renderer,
                storage,
                InventoryImportParser(),
            )
        return self._application

    def __getattr__(self, name):
        return getattr(self._resolve(), name)


def create_app(
    settings: Settings | None = None,
    auth_repository: AuthRepository | None = None,
    quote_application=None,
    audit_repository: PlatformAuditRepository | None = None,
    login_rate_limiter: LoginRateLimiter | None = None,
    document_intelligence=None,
    scan_import_application=None,
    tender_application=None,
    inventory_application=None,
    user_features=None,
    tender_proofreading_service=None,
    tender_scan_application=None,
    ai_assist_service=None,
) -> FastAPI:
    resolved_settings = settings or Settings.from_env()
    resolved_settings.validate()
    postgres_engine: Engine | None = None
    if resolved_settings.auth_mode == "session" and resolved_settings.database_url:
        postgres_engine = create_postgres_engine(resolved_settings)
    if auth_repository is None:
        if resolved_settings.auth_mode == "session":
            if postgres_engine is None:
                raise RuntimeError("DATABASE_URL is required for session authentication")
            auth_repository = PostgresAuthRepository(postgres_engine)
        else:
            auth_repository = InMemoryAuthRepository()
    if audit_repository is None:
        if postgres_engine is not None:
            audit_repository = PostgresAuditRepository(postgres_engine)
        else:
            audit_repository = development_audit_repository
    if resolved_settings.app_env in {"staging", "production"} and isinstance(audit_repository, AuditRepository):
        raise RuntimeError("In-memory platform audit is forbidden in staging/production")
    if hasattr(auth_repository, "set_platform_audit_repository"):
        auth_repository.set_platform_audit_repository(audit_repository)
    if quote_application is None:
        if postgres_engine is not None:
            quote_application = LazyPostgresQuoteApplication(resolved_settings, postgres_engine)
        elif resolved_settings.app_env in {"staging", "production"}:
            quote_application = LazyPostgresQuoteApplication(resolved_settings)
        else:
            quote_repository = StevenQuoteRepository(seed_demo=resolved_settings.demo_seed_enabled)
            quote_audit = AuditRepository()
            exporter = QuoteExcelExporter(Path(resolved_settings.file_storage_root))
            quote_application = StevenQuoteApplicationService(
                InMemoryQuoteUnitOfWork(quote_repository, quote_audit),
                QuoteImportParser(),
                exporter,
                LocalAppendOnlyQuoteStorage(exporter.data_root),
            )
            if document_intelligence is None:
                document_repository = InMemoryDocumentIntelligenceRepository()
                default_candidate = {
                    "supplier_code": "SUP-SCAN",
                    "supplier_name": "扫描报价供应商（脱敏演示）",
                    "currency": "HKD",
                    "valid_until": "2026-08-31",
                    "freight": "0",
                    "tax": "0",
                    "items": [
                        {"item_code": f"ITEM-{index:03}", "item": name, "specification": specification, "qty": qty, "unit": unit, "unit_price": price}
                        for index, (name, specification, qty, unit, price) in enumerate([
                            ("A4 影印纸", "80gsm，500 张/包", "20", "包", "42"),
                            ("蓝色原子笔", "0.7mm", "100", "支", "4.2"),
                            ("订书钉", "24/6，1000 枚/盒", "50", "盒", "8.5"),
                            ("A4 文件夹", "透明，40 页", "60", "个", "6"),
                            ("白板笔", "黑色，可擦", "30", "支", "12"),
                        ], start=1)
                    ],
                }
                document_intelligence = DocumentIntelligenceService(
                    document_repository,
                    InMemoryDocumentFileStorage(),
                    MockOcrAdapter(),
                    MockAiStructuringAdapter(default_candidate),
                )
            if scan_import_application is None:
                scan_import_application = StevenScanImportApplicationService(
                    InMemoryScanImportUnitOfWork(document_intelligence.repository, quote_repository, quote_audit),
                    QuoteImportParser(),
                    exporter,
                    LocalAppendOnlyQuoteStorage(exporter.data_root),
                )
    if document_intelligence is None and postgres_engine is not None:
        if resolved_settings.ocr_enabled and resolved_settings.ocr_provider == "paddle":
            ocr_adapter = PaddleOcrAdapter()
        elif resolved_settings.ocr_enabled and resolved_settings.ocr_provider == "mock":
            ocr_adapter = MockOcrAdapter()
        else:
            ocr_adapter = DisabledOcrAdapter()
        if resolved_settings.ai_structuring_enabled and resolved_settings.ai_structuring_provider == "deepseek":
            quotation_adapter = DeepSeekStructuringAdapter(
                resolved_settings.ai_structuring_endpoint,
                resolved_settings.ai_structuring_model,
                resolved_settings.ai_structuring_timeout_seconds,
                httpx_json_transport,
            )
        elif resolved_settings.ai_structuring_enabled and resolved_settings.ai_structuring_provider == "mock":
            quotation_adapter = MockAiStructuringAdapter({
                "supplier_code": "SUP-SCAN",
                "supplier_name": "扫描报价供应商（脱敏演示）",
                "quote_date": "2026-07-18",
                "currency": "HKD",
                "valid_until": "2026-08-31",
                "freight": "0",
                "tax": "0",
                "items": [{"item_code": "ITEM-001", "item": "脱敏演示品项", "specification": "待人工确认", "qty": "1", "unit": "项", "unit_price": "0"}],
            })
        else:
            quotation_adapter = DisabledAiStructuringAdapter()
        document_intelligence = PostgresDocumentIntelligenceService(
            postgres_engine,
            LocalAppendOnlyDocumentFileStorage(Path(resolved_settings.file_storage_root) / "documents"),
            ocr_adapter,
            RoutingAiStructuringAdapter({
                "steven.s1.tender_source": TenderSourceRuleAdapter(),
                "steven.s2.quotation": quotation_adapter,
            }),
        )
    if scan_import_application is None and postgres_engine is not None:
        exporter = QuoteExcelExporter(Path(resolved_settings.file_storage_root))
        scan_import_application = StevenScanImportApplicationService(
            PostgresScanImportUnitOfWork(postgres_engine),
            QuoteImportParser(),
            exporter,
            LocalAppendOnlyQuoteStorage(exporter.data_root),
        )
    if tender_application is None:
        if postgres_engine is not None:
            tender_application = LazyPostgresTenderApplication(resolved_settings, postgres_engine)
        elif resolved_settings.app_env in {"staging", "production"}:
            tender_application = LazyPostgresTenderApplication(resolved_settings)
        else:
            renderer = TenderWordRenderer()
            tender_repository = InMemoryTenderRepository(seed_demo=resolved_settings.demo_seed_enabled)
            tender_application = StevenTenderApplicationService(
                InMemoryTenderUnitOfWork(tender_repository, AuditRepository()),
                renderer,
                LocalAppendOnlyFileStorage(
                    Path(resolved_settings.file_storage_root),
                    "tenders",
                    "docx",
                    renderer.verify,
                ),
            )
    if inventory_application is None:
        if postgres_engine is not None:
            inventory_application = LazyPostgresInventoryApplication(
                resolved_settings,
                postgres_engine,
            )
        elif resolved_settings.app_env in {"staging", "production"}:
            inventory_application = LazyPostgresInventoryApplication(resolved_settings)
        else:
            renderer = InventoryExcelRenderer()
            inventory_repository = InMemoryInventoryRepository()
            inventory_application = StevenInventoryApplicationService(
                InMemoryInventoryUnitOfWork(
                    inventory_repository,
                    AuditRepository(),
                ),
                renderer,
                LocalAppendOnlyFileStorage(
                    Path(resolved_settings.file_storage_root),
                    "inventory",
                    "xlsx",
                    renderer.verify,
                ),
            )

    if user_features is None and postgres_engine is not None:
        user_features = UserFeaturesService(postgres_engine)
    if tender_scan_application is None and postgres_engine is not None:
        tender_scan_application = TenderScanApplicationService(postgres_engine)
    if tender_proofreading_service is None and postgres_engine is not None:
        proofreading_adapter = None
        if resolved_settings.ai_structuring_provider == "mock":
            proofreading_adapter = MockTenderProofreadingAdapter()
        elif resolved_settings.ai_structuring_enabled:
            proofreading_adapter = DeepSeekStructuringAdapter(
                resolved_settings.ai_structuring_endpoint,
                resolved_settings.ai_structuring_model,
                resolved_settings.ai_structuring_timeout_seconds,
                httpx_json_transport,
            )
        tender_proofreading_service = TenderProofreadingService(
            postgres_engine,
            proofreading_adapter,
            enabled=resolved_settings.ai_structuring_enabled,
            provider=resolved_settings.ai_structuring_provider,
            model=resolved_settings.ai_structuring_model,
        )
    if ai_assist_service is None:
        ai_assist_service = StevenAiAssistService(
            enabled=resolved_settings.ai_structuring_enabled,
            provider=resolved_settings.ai_structuring_provider,
            endpoint=resolved_settings.ai_structuring_endpoint,
            model=resolved_settings.ai_structuring_model,
            timeout_seconds=resolved_settings.ai_structuring_timeout_seconds,
            transport=httpx_json_transport,
        )

    application = FastAPI(title="培英 Steven AI 行政助手 API", version="0.3.0")
    application.state.settings = resolved_settings
    application.state.postgres_engine = postgres_engine
    application.state.auth_repository = auth_repository
    application.state.audit_repository = audit_repository
    application.state.quote_application = quote_application
    application.state.document_intelligence = document_intelligence
    application.state.scan_import_application = scan_import_application
    application.state.tender_application = tender_application
    application.state.inventory_application = inventory_application
    application.state.user_features = user_features
    application.state.tender_proofreading_service = tender_proofreading_service
    application.state.tender_scan_application = tender_scan_application
    application.state.ai_assist_service = ai_assist_service
    if login_rate_limiter is None:
        if resolved_settings.rate_limit_mode == "memory":
            login_rate_limiter = MemoryLoginRateLimiter(
                resolved_settings.login_rate_limit_attempts,
                resolved_settings.login_rate_limit_window_seconds,
            )
        elif resolved_settings.rate_limit_mode == "gateway":
            login_rate_limiter = GatewayLoginRateLimiter()
        else:
            raise RuntimeError("RATE_LIMIT_MODE=redis requires an approved shared limiter adapter")
    application.state.login_rate_limiter = login_rate_limiter
    application.middleware("http")(request_security_middleware)
    application.middleware("http")(request_id_middleware)
    application.include_router(auth_router)
    application.include_router(admin_router)
    application.include_router(steven_router)
    application.include_router(quotes_router)
    application.include_router(tenders_router)
    application.include_router(inventory_router)
    application.include_router(document_intelligence_router)
    application.include_router(documents_router)
    application.include_router(user_features_router)
    application.include_router(audit_router)

    @application.exception_handler(ApiError)
    async def handle_api_error(request: Request, error: ApiError):
        return error_response(request, error)

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, error: RequestValidationError):
        details = [
            {
                "field": ".".join(str(part) for part in item["loc"] if part not in {"body", "query", "path"}),
                "message": item["msg"],
                "type": item["type"],
            }
            for item in error.errors()
        ]
        return error_response(request, ApiError(422, "validation_error", "请求字段校验失败。", {"fields": details}))

    @application.get("/health")
    async def health(request: Request) -> dict:
        database_name = None
        if postgres_engine is not None:
            database_name = make_url(resolved_settings.database_url).database
        return success(request, {
            "status": "ok",
            "service": "steven-api",
            "app_env": resolved_settings.app_env,
            "auth_mode": resolved_settings.auth_mode,
            "persistence": {
                "mode": "postgresql" if postgres_engine is not None else "memory",
                "database": database_name,
                "session_store": "postgresql" if isinstance(auth_repository, PostgresAuthRepository) else "memory",
                "audit_store": "postgresql" if isinstance(audit_repository, PostgresAuditRepository) else "memory",
                "quote_store": "postgresql" if isinstance(quote_application, LazyPostgresQuoteApplication) else "memory",
                "tender_store": "postgresql" if isinstance(tender_application, LazyPostgresTenderApplication) else "memory",
                "inventory_store": "postgresql" if isinstance(inventory_application, LazyPostgresInventoryApplication) else "memory",
            },
            "demo_seed_enabled": resolved_settings.demo_seed_enabled,
            "ai_provider": resolved_settings.ai_structuring_provider,
            "demo_profile_enabled": resolved_settings.demo_profile_enabled,
            "ocr_provider": resolved_settings.ocr_provider,
            "ocr_enabled": resolved_settings.ocr_enabled,
            "ai_structuring_provider": resolved_settings.ai_structuring_provider,
            "ai_enabled": resolved_settings.ai_structuring_enabled,
        })

    return application


app = create_app()
