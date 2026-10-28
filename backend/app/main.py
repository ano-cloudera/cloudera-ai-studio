from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import chat, models, random_queries, usage
from app.api.v1 import documents as v1_documents
from app.api.v1 import libraries as v1_libraries
from app.api.v1 import rag as v1_rag
from app.api.v1 import retrieval as v1_retrieval
from app.api.v1 import prompts as v1_prompts
from app.api.v1 import skills as v1_skills
from app.api.v1 import semantic as v1_semantic
from app.api.v1 import connectors as v1_connectors
from app.api.v1 import ai_registry as v1_ai_registry
from app.api.v1 import chat_attachments as v1_chat_attachments
from app.api.v1 import chat_context as v1_chat_context
from app.api.v1 import mcp as v1_mcp
from app.api.v1 import tools as v1_tools
from app.api.v1 import projects as v1_projects
from app.api.v1 import ask_data as v1_ask_data
from app.api.v1 import workspaces as v1_workspaces
from app.stores.factory import build_conversation_store, build_usage_store, init_platform_metadata, log_active_stores
from app.core.config import Settings, get_settings
from app.platform.config_validation import validate_startup_config
from app.platform.readiness import build_readiness_report
from app.platform.accelerator import ACCELERATOR_VERSION
from app.llm.registry import ProviderRegistry
from app.services.chat import ChatService
from app.services.puppygraph_client import PuppyGraphClient
logger = logging.getLogger(__name__)


def _semantic_runtime_health(settings: Settings) -> dict:
    from app.semantic_runtime.loader import SemanticRuntimeLoader

    bundle = SemanticRuntimeLoader.get(settings).get_bundle()
    status = bundle.health or "healthy"
    if bundle.mode == "legacy":
        status = "legacy_fallback"
    return {
        "status": status,
        "mode": bundle.mode,
        "registry_version_number": bundle.registry_version_number,
        "deployment_id": str(bundle.deployment_id) if bundle.deployment_id else None,
    }


@asynccontextmanager
async def _lifespan(application: FastAPI):
    settings: Settings = application.state.settings
    try:
        init_platform_metadata(settings)
    except Exception:
        logger.exception("platform bootstrap failed")
    chat_service: ChatService = application.state.chat_service
    try:
        chat_service.bootstrap_runtime_from_db()
    except Exception:
        logger.exception("semantic runtime bootstrap failed — legacy OSSIE fallback")
    try:
        from app.embeddings.provider import get_embedding_provider
        from app.vectors.store import build_vector_store

        vector_store = build_vector_store(settings)
        if vector_store is not None:
            embed = get_embedding_provider(settings)
            vector_store.ensure_collection(dimension=embed.dimension)
    except Exception:
        logger.exception("qdrant collection ensure failed — RAG may be unavailable")
    try:
        from app.services.knowledge_ingestion_recovery import scan_and_enqueue_startup_recovery

        scan_and_enqueue_startup_recovery(settings)
    except Exception:
        logger.exception("knowledge ingestion startup recovery failed")
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    configured = settings or get_settings()
    validate_startup_config(configured)
    try:  # tables must exist before the stores below bind to the platform DB (fresh DB would fall back to legacy files)
        init_platform_metadata(configured)
    except Exception:
        logger.exception("platform bootstrap failed")
    application = FastAPI(title=configured.app_name, version=ACCELERATOR_VERSION, lifespan=_lifespan)
    application.state.settings = configured
    application.state.provider_registry = ProviderRegistry(configured)
    usage_store = build_usage_store(configured)
    conversation_store = build_conversation_store(configured)
    log_active_stores(configured, conversation_store, usage_store)
    application.state.usage_store = usage_store
    application.state.chat_service = ChatService(
        configured,
        history=conversation_store,
        usage_store=usage_store,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=configured.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/health/ready")
    def readiness() -> JSONResponse:
        report = build_readiness_report(configured, provider_registry=application.state.provider_registry)
        report["components"]["semantic_runtime"] = _semantic_runtime_health(configured)
        report["components"]["puppygraph"] = PuppyGraphClient(configured).schema_summary()
        code = 200 if report.get("core_ready") else 503
        return JSONResponse(status_code=code, content=report)

    @application.get("/version")
    def version() -> dict[str, str]:
        return {
            "accelerator_version": ACCELERATOR_VERSION,
            "app_name": configured.app_name,
            "deployment_profile": configured.deployment_profile,
            "feature_profile": configured.feature_profile,
        }

    @application.exception_handler(Exception)
    async def safe_error(_: Request, error: Exception):
        request_id = str(uuid.uuid4())
        logger.exception("unhandled_error request_id=%s", request_id, exc_info=error)
        return JSONResponse(
            status_code=500,
            content={"status": "ERROR", "message": "Internal server error", "request_id": request_id},
        )

    application.include_router(models.router)
    application.include_router(random_queries.router)
    application.include_router(chat.router)
    application.include_router(usage.router)
    application.include_router(v1_workspaces.router, prefix="/api/v1")
    application.include_router(v1_ask_data.router, prefix="/api/v1")
    application.include_router(v1_projects.router, prefix="/api/v1")
    application.include_router(v1_libraries.router, prefix="/api/v1")
    application.include_router(v1_documents.router, prefix="/api/v1")
    application.include_router(v1_retrieval.router, prefix="/api/v1")
    application.include_router(v1_rag.router, prefix="/api/v1")
    application.include_router(v1_prompts.router, prefix="/api/v1")
    application.include_router(v1_skills.router, prefix="/api/v1")
    application.include_router(v1_tools.router, prefix="/api/v1")
    application.include_router(v1_semantic.router, prefix="/api/v1")
    application.include_router(v1_connectors.router, prefix="/api/v1")
    application.include_router(v1_ai_registry.router, prefix="/api/v1")
    application.include_router(v1_chat_attachments.router, prefix="/api/v1")
    application.include_router(v1_chat_context.router, prefix="/api/v1")
    application.include_router(v1_mcp.router, prefix="/api/v1")
    return application


app = create_app()
