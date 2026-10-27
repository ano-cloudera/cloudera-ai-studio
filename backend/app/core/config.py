from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.core.impala_env import load_impala_profile
from app.core.llm_env import gemini_model_from_env_files


BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_ROOT / ".env", BACKEND_ROOT.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = Field(default="Cloudera AI Accelerator", validation_alias="APP_NAME")
    app_env: str = "local"
    accelerator_version: str = Field(default="1.0.0-m6", validation_alias="ACCELERATOR_VERSION")
    deployment_profile: str = Field(default="local", validation_alias="DEPLOYMENT_PROFILE")
    feature_profile: str = Field(
        default="FULL_ACCELERATOR",
        validation_alias="FEATURE_PROFILE",
        description="ASK_DATA_ONLY | RAG_ONLY | ASK_DATA_AND_RAG | FULL_ACCELERATOR",
    )
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    default_llm_provider: str = "gemini"

    qwen_base_url: str = ""
    qwen_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("QWEN_API_KEY", "QWEN_API_TOKEN"),
    )
    qwen_model: str = ""
    qwen_verify_ssl: bool = True

    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    )
    gemini_model: str = Field(
        default="gemini-3.8-flash",
        validation_alias=AliasChoices("GEMINI_MODEL", "MODEL_GEMINI"),
    )

    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = ""
    openai_verify_ssl: bool = True

    llm_request_timeout_seconds: float = Field(default=60, gt=0, le=300)
    llm_max_tokens: int = Field(default=1800, ge=100, le=8000)

    project_root: Path = BACKEND_ROOT / "projects"
    ossie_project_id: str = "tempo_scan_impala"
    sql_max_rows: int = Field(default=200, ge=1, le=1000)
    data_backend: str = Field(default="impala", validation_alias="DATA_BACKEND")
    duckdb_path: Path = Field(
        default=BACKEND_ROOT / "runtime" / "tempo_gold_local.duckdb",
        validation_alias="DUCKDB_PATH",
    )
    impala_host: str = "localhost"
    impala_port: int = 21050
    impala_database: str = "gold"
    impala_auth_mechanism: str = "PLAIN"
    impala_user: str = ""
    impala_password: str = ""
    impala_use_ssl: bool = False
    impala_use_http_transport: bool = False
    impala_http_path: str = ""
    impala_kerberos_service_name: str = "impala"
    impala_query_timeout_seconds: int = Field(default=60, ge=1, le=600)
    trino_host: str = Field(default="", validation_alias="TRINO_HOST")
    trino_port: int = Field(default=8080, validation_alias="TRINO_PORT")
    trino_catalog: str = Field(default="", validation_alias="TRINO_CATALOG")
    trino_user: str = Field(default="", validation_alias="TRINO_USER")
    trino_password: str = Field(default="", validation_alias="TRINO_PASSWORD")
    semantic_validation_timeout_seconds: int = Field(default=45, ge=5, le=300, validation_alias="SEMANTIC_VALIDATION_TIMEOUT_SECONDS")
    semantic_source_validation_mode: str = Field(
        default="metadata_only",
        validation_alias="SEMANTIC_SOURCE_VALIDATION_MODE",
        description="metadata_only | safe_query",
    )
    semantic_runtime_storage_root: Path = Field(
        default=BACKEND_ROOT / "var" / "semantic-runtime",
        validation_alias="SEMANTIC_RUNTIME_STORAGE_ROOT",
    )
    semantic_default_model_key: str = Field(
        default="tempo_core",
        validation_alias="SEMANTIC_DEFAULT_MODEL_KEY",
    )
    connector_max_rows: int = Field(default=1000, ge=1, le=10_000, validation_alias="CONNECTOR_MAX_ROWS")
    connector_connect_timeout_seconds: int = Field(
        default=30,
        ge=1,
        le=300,
        validation_alias="CONNECTOR_CONNECT_TIMEOUT_SECONDS",
    )
    connector_query_timeout_seconds: int = Field(
        default=60,
        ge=1,
        le=600,
        validation_alias="CONNECTOR_QUERY_TIMEOUT_SECONDS",
    )
    connector_metadata_timeout_seconds: int = Field(
        default=30,
        ge=1,
        le=300,
        validation_alias="CONNECTOR_METADATA_TIMEOUT_SECONDS",
    )
    connector_metadata_cache_ttl_seconds: int = Field(
        default=60,
        ge=0,
        le=3600,
        validation_alias="CONNECTOR_METADATA_CACHE_TTL_SECONDS",
    )
    # When set to `aws` or `ingram`, load IMPALA_* from that labeled block in repo `.env`
    # (see ### IMPALA CREDENTIALS … ENV sections). Avoids duplicate-key override bugs.
    impala_credential_profile: str = "ingram"
    state_store: str = Field(
        default="sqlite",
        validation_alias="STATE_STORE",
        description="Legacy label; when DATABASE_URL is set, conversation/usage use platform DB",
    )
    cai_data_dir: Path | None = Field(
        default=None,
        validation_alias="CAI_DATA_DIR",
        description="Optional local persistence root (derives paths when sub-keys are relative)",
    )
    database_url: str = Field(
        default="",
        validation_alias=AliasChoices("DATABASE_URL", "POSTGRES_URL"),
        description="Platform metadata database URL (PostgreSQL or SQLite)",
    )
    default_project_slug: str = Field(
        default="",
        validation_alias="DEFAULT_PROJECT_SLUG",
        description="Active project slug when using postgres platform metadata (empty = ossie_project_id)",
    )

    document_storage_root: Path = Field(
        default=BACKEND_ROOT / "runtime" / "document_storage",
        validation_alias="DOCUMENT_STORAGE_ROOT",
        description="NFS mount root for uploaded document binaries (M2A)",
    )
    document_max_file_mb: int = Field(
        default=25,
        ge=1,
        le=500,
        validation_alias="DOCUMENT_MAX_FILE_MB",
    )
    document_allowed_types: str = Field(
        default="pdf,txt,md,docx,xlsx",
        validation_alias="DOCUMENT_ALLOWED_TYPES",
    )
    chat_attachment_ttl_days: int = Field(default=7, ge=1, le=90, validation_alias="CHAT_ATTACHMENT_TTL_DAYS")
    chat_attachment_max_files: int = Field(default=5, ge=1, le=20, validation_alias="CHAT_ATTACHMENT_MAX_FILES")
    chat_attachment_max_file_mb: int = Field(default=25, ge=1, le=500, validation_alias="CHAT_ATTACHMENT_MAX_FILE_MB")
    chat_attachment_max_batch_mb: int = Field(default=75, ge=1, le=2000, validation_alias="CHAT_ATTACHMENT_MAX_BATCH_MB")
    knowledge_upload_max_files_per_batch: int = Field(
        default=10,
        ge=1,
        le=50,
        validation_alias="KNOWLEDGE_UPLOAD_MAX_FILES_PER_BATCH",
    )
    knowledge_upload_max_batch_mb: int = Field(
        default=100,
        ge=1,
        le=2000,
        validation_alias="KNOWLEDGE_UPLOAD_MAX_BATCH_MB",
    )
    document_chunk_size_tokens: int = Field(default=512, ge=64, le=4096, validation_alias="DOCUMENT_CHUNK_SIZE")
    document_chunk_overlap_tokens: int = Field(default=64, ge=0, le=1024, validation_alias="DOCUMENT_CHUNK_OVERLAP")
    embedding_provider: str = Field(default="mock", validation_alias="EMBEDDING_PROVIDER")
    embedding_model: str = Field(default="BAAI/bge-m3", validation_alias="EMBEDDING_MODEL")
    embedding_batch_size: int = Field(default=16, ge=1, le=128, validation_alias="EMBEDDING_BATCH_SIZE")
    qdrant_url: str = Field(default="", validation_alias="QDRANT_URL")
    qdrant_api_key: SecretStr = Field(default=SecretStr(""), validation_alias="QDRANT_API_KEY")
    qdrant_collection: str = Field(default="accelerator_chunks", validation_alias="QDRANT_COLLECTION")
    qdrant_timeout_seconds: int = Field(default=30, ge=1, le=120, validation_alias="QDRANT_TIMEOUT_SECONDS")
    document_auto_process: bool = Field(default=True, validation_alias="DOCUMENT_AUTO_PROCESS")
    document_pdf_use_pypdf: bool = Field(
        default=False,
        validation_alias="DOCUMENT_PDF_USE_PYPDF",
        description="Use pypdf text extraction for PDFs instead of Docling (faster for text-native demo PDFs).",
    )
    knowledge_max_documents_per_library: int = Field(
        default=100,
        ge=1,
        le=10_000,
        validation_alias="KNOWLEDGE_MAX_DOCUMENTS_PER_LIBRARY",
        description="Maximum indexed documents allowed per knowledge library",
    )
    bulk_delete_max_items: int = Field(
        default=100,
        ge=1,
        le=500,
        validation_alias="BULK_DELETE_MAX_ITEMS",
        description="Maximum items per bulk delete request",
    )
    retrieval_top_k: int = Field(default=20, ge=1, le=100, validation_alias="RETRIEVAL_TOP_K")
    rerank_top_n: int = Field(default=5, ge=1, le=50, validation_alias="RERANK_TOP_N")
    rag_max_context_tokens: int = Field(default=4096, ge=256, le=32000, validation_alias="RAG_MAX_CONTEXT_TOKENS")
    reranker_provider: str = Field(default="none", validation_alias="RERANKER_PROVIDER")
    reranker_model: str = Field(default="BAAI/bge-reranker-v2-m3", validation_alias="RERANKER_MODEL")
    rag_system_prompt_path: Path = Field(
        default=BACKEND_ROOT / "prompts" / "rag_system.txt",
        validation_alias="RAG_SYSTEM_PROMPT_PATH",
    )
    rag_conversation_turns: int = Field(default=3, ge=0, le=10, validation_alias="RAG_CONVERSATION_TURNS")
    rag_default_library_ids: str = Field(
        default="",
        validation_alias="RAG_DEFAULT_LIBRARY_IDS",
        description="Optional comma-separated library UUIDs when request omits library_ids",
    )
    rag_min_rerank_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        validation_alias="RAG_MIN_RERANK_SCORE",
        description="If >0, treat top rerank/vector score below threshold as insufficient evidence",
    )

    conversation_db_path: Path = BACKEND_ROOT / "runtime" / "conversation_history.sqlite"
    usage_db_path: Path = Field(
        default=BACKEND_ROOT / "runtime" / "llm_usage.sqlite",
        validation_alias="USAGE_DB_PATH",
    )
    usage_monthly_token_budget: int = Field(
        default=0,
        ge=0,
        validation_alias="USAGE_MONTHLY_TOKEN_BUDGET",
        description="Optional soft cap for Usage UI (0 = hidden)",
    )

    # Optional fallback: a separately governed sibling system (TEMPO Local
    # Agent) queried only when our own OSSIE-driven planner can't match a
    # published metric at all (strategy=unsupported). Disabled by default -
    # empty base_url means the fallback node is skipped entirely, so
    # existing behavior is unchanged unless an operator opts in.
    local_agent_base_url: str = ""
    # When true and base_url is set, force tempo_agent_v3 (legacy; prefer ask_data_routing=v3).
    local_agent_primary: bool = False
    # auto | ossie | v3 — see app/services/ask_data_routing.py
    ask_data_routing: str = "auto"

    # Ask Data presentation tier (AMP / deployment tuning)
    ask_data_presentation_tier_enabled: bool = Field(
        default=True,
        validation_alias="ASK_DATA_PRESENTATION_TIER_ENABLED",
    )
    ask_data_panel_auto_open: str = Field(
        default="heuristic",
        validation_alias="ASK_DATA_PANEL_AUTO_OPEN",
        description="heuristic | always | never",
    )
    ask_data_tier3_min_rows: int = Field(default=13, ge=1, le=10_000, validation_alias="ASK_DATA_TIER3_MIN_ROWS")
    ask_data_tier3_min_insights: int = Field(
        default=3, ge=0, le=50, validation_alias="ASK_DATA_TIER3_MIN_INSIGHTS"
    )
    ask_data_tier3_min_implications: int = Field(
        default=2, ge=0, le=50, validation_alias="ASK_DATA_TIER3_MIN_IMPLICATIONS"
    )
    ask_data_rank_tier3_above_n: int = Field(
        default=5, ge=0, le=500, validation_alias="ASK_DATA_RANK_TIER3_ABOVE_N"
    )
    ask_data_rank_min_tier: int = Field(default=2, ge=1, le=3, validation_alias="ASK_DATA_RANK_MIN_TIER")
    ask_data_tier1_max_rows: int = Field(default=1, ge=0, le=100, validation_alias="ASK_DATA_TIER1_MAX_ROWS")
    ask_data_tier1_max_columns: int = Field(
        default=2, ge=1, le=50, validation_alias="ASK_DATA_TIER1_MAX_COLUMNS"
    )
    ask_data_force_tier3_pareto: bool = Field(default=True, validation_alias="ASK_DATA_FORCE_TIER3_PARETO")
    ask_data_force_tier3_operational: bool = Field(
        default=True, validation_alias="ASK_DATA_FORCE_TIER3_OPERATIONAL"
    )
    ask_data_force_tier3_chart: bool = Field(default=True, validation_alias="ASK_DATA_FORCE_TIER3_CHART")
    ask_data_chat_expand_tier1: bool = Field(default=True, validation_alias="ASK_DATA_CHAT_EXPAND_TIER1")
    ask_data_chat_expand_tier2: bool = Field(default=True, validation_alias="ASK_DATA_CHAT_EXPAND_TIER2")
    ask_data_chat_details_default_open: bool = Field(
        default=False,
        validation_alias="ASK_DATA_CHAT_DETAILS_DEFAULT_OPEN",
    )
    ask_data_audience_mode: str = Field(
        default="executive",
        validation_alias="ASK_DATA_AUDIENCE_MODE",
        description="executive | analyst",
    )
    ask_data_tier1_show_narrative: bool = Field(
        default=False,
        validation_alias="ASK_DATA_TIER1_SHOW_NARRATIVE",
        description="When true, tier-1 KPI chat shows executive summary and insights (not only the headline).",
    )
    ask_data_legacy_tempo_capability_catalog: bool = Field(
        default=False,
        validation_alias="ASK_DATA_LEGACY_TEMPO_CAPABILITY_CATALOG",
        description="When true, legacy TEMPO Scan 9-domain capability menu is used for local Tempo OSSIE deployments.",
    )
    local_agent_timeout_seconds: float = Field(default=180, gt=0, le=600)
    local_agent_engine: str = "langgraph"
    local_agent_max_attempts: int = Field(default=2, ge=1, le=5)
    local_agent_retry_delay_seconds: float = Field(default=2.0, ge=0, le=30)

    # OSSIE workflow answer-quality loop (Phase B1)
    judge_max_iterations: int = Field(default=2, ge=0, le=5)
    judge_enabled: bool = True

    # In-process TEMPO domain graph (knowledge/tempo_domain_graph.yaml)
    business_graph_enabled: bool = Field(default=True, validation_alias="BUSINESS_GRAPH_ENABLED")

    # Phase C7 — optional PuppyGraph (off critical path; schema stub in knowledge/)
    puppygraph_enabled: bool = Field(default=False, validation_alias="PUPPYGRAPH_ENABLED")
    puppygraph_base_url: str = Field(default="", validation_alias="PUPPYGRAPH_BASE_URL")

    @property
    def cors_origin_list(self) -> list[str]:
        return [value.strip() for value in self.cors_origins.split(",") if value.strip()]


def _resolve_backend_relative(path: Path) -> Path:
    """Resolve paths relative to BACKEND_ROOT (standalone repo layout).

    Env templates copied from the monorepo often prefix ``backend/`` even though
    BACKEND_ROOT already points at ``…/cloudera-ai-studio/backend``. Strip that
    duplicate segment so storage does not land in ``backend/backend/…``.
    """
    if path.is_absolute():
        return path.resolve()
    parts = path.parts
    if parts and parts[0] == "backend":
        path = Path(*parts[1:]) if len(parts) > 1 else Path(".")
    return (BACKEND_ROOT / path).resolve()


def _resolve_cai_data_dir(path: Path) -> Path:
    if path.is_absolute():
        return path.resolve()
    return (REPO_ROOT / path).resolve()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    updates: dict = {}
    cai_root: Path | None = None
    if settings.cai_data_dir is not None:
        cai_root = _resolve_cai_data_dir(Path(settings.cai_data_dir))
        updates["cai_data_dir"] = cai_root
        if not (settings.database_url or "").strip():
            db_file = (cai_root / "metadata" / "studio.db").resolve()
            updates["database_url"] = f"sqlite+pysqlite:///{db_file}"
    duck_path = Path(settings.duckdb_path)
    if not duck_path.is_absolute():
        updates["duckdb_path"] = _resolve_backend_relative(duck_path)
    doc_root = Path(settings.document_storage_root)
    if cai_root is not None and not doc_root.is_absolute():
        updates["document_storage_root"] = (cai_root / doc_root).resolve()
    elif not doc_root.is_absolute():
        updates["document_storage_root"] = _resolve_backend_relative(doc_root)
    sem_root = Path(settings.semantic_runtime_storage_root)
    if cai_root is not None and not sem_root.is_absolute():
        updates["semantic_runtime_storage_root"] = (cai_root / sem_root).resolve()
    elif not sem_root.is_absolute():
        updates["semantic_runtime_storage_root"] = _resolve_backend_relative(sem_root)
    profile = settings.impala_credential_profile.strip().lower()
    if profile:
        updates.update(load_impala_profile(REPO_ROOT / ".env", profile) or {})
    gemini_from_env = gemini_model_from_env_files(backend_root=BACKEND_ROOT, repo_root=REPO_ROOT)
    if gemini_from_env:
        updates["gemini_model"] = gemini_from_env
    elif not (settings.gemini_model or "").strip() and settings.gemini_api_key.get_secret_value():
        updates["gemini_model"] = "gemini-3.8-flash"
    if updates:
        return settings.model_copy(update=updates)
    return settings
