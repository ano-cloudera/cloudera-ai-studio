from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.text_sanitize import without_em_dash


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelInfo(StrictModel):
    provider: Literal["qwen", "gemini", "openai"]
    id: str
    label: str
    available: bool
    reason: str | None = None


class ModelList(StrictModel):
    models: list[ModelInfo]


Status = Literal["SUCCESS", "CLARIFICATION", "clarification_required", "NO_DATA", "UNSUPPORTED", "ERROR"]
ContextMode = Literal["RAW_TABLE", "GOVERNED_SEMANTIC"]
QueryStrategy = Literal["governed", "sql_fallback", "clarification", "unsupported"]
Strategy = Literal[
    "governed",
    "sql_fallback",
    "clarification",
    "unsupported",
    "conversational",
    "local_agent_exploratory",
    "history_only_analysis",
    "rag",
    "mcp",
]
ChatMode = Literal["ask_data", "rag", "mcp"]
GroundingLevel = Literal["SUPPORTED", "PARTIALLY_SUPPORTED", "INSUFFICIENT_EVIDENCE"]
ResponseRoute = Literal["ask_data", "rag"]
ChartType = Literal["bar", "line", "area", "scatter", "pie", "table", "kpi"]
PresentationTier = Literal[1, 2, 3]


class ChartSpec(StrictModel):
    type: ChartType
    # Gemini structured output rejects nested objects missing required keys.
    title: str = Field(default="Chart")
    x: str | None = None
    y: str | None = None
    series: str | None = None


class QueryPlan(StrictModel):
    strategy: QueryStrategy
    domains: list[str] = []
    metrics: list[str] = []
    dimensions: list[str] = []
    filters: dict[str, Any] = {}
    analysis_type: str = "metric"
    sql: str | None = None
    clarification_question: str | None = None


class AnalysisOutput(StrictModel):
    direct_answer: str
    executive_summary: str
    insights: list[str]
    business_implications: list[str]
    caveats: list[str]
    data_reference: str
    chart_spec: ChartSpec | None = None

    @field_validator(
        "direct_answer",
        "executive_summary",
        "data_reference",
        mode="before",
    )
    @classmethod
    def _strip_em_dash_text(cls, value: object) -> object:
        return without_em_dash(value) if isinstance(value, str) else value

    @field_validator("insights", "business_implications", "caveats", mode="before")
    @classmethod
    def _strip_em_dash_lists(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        return [without_em_dash(item) if isinstance(item, str) else item for item in value]


class CitationRecord(StrictModel):
    document_id: str
    filename: str | None = None
    page_number: int | None = None
    section: str | None = None
    chunk_id: str
    source_uri: str | None = None
    snippet: str
    score: float


class RagRetrievalMeta(StrictModel):
    candidate_count: int = 0
    selected_count: int = 0


ChatContextSourceType = Literal[
    "knowledge_library",
    "uploaded_file",
    "mcp_connector",
    "table",
    "semantic_model",
    "semantic_entity",
    "semantic_metric",
    "semantic_term",
]


class ChatContextSource(StrictModel):
    type: ChatContextSourceType
    id: str
    name: str
    metadata: dict[str, Any] | None = None


class AskDataRequest(StrictModel):
    session_id: str
    question: str
    provider: Literal["qwen", "gemini", "openai"]
    model: str
    # When true, also consult TEMPO Local Agent as second option after primary path
    # stalls on clarification/unsupported (requires LOCAL_AGENT_BASE_URL).
    use_local_agent: bool = False
    mode: ChatMode = "ask_data"
    library_ids: list[str] | None = None
    rag_document_ids: list[str] | None = None
    context_sources: list[ChatContextSource] | None = None


class QueryData(StrictModel):
    columns: list[str] = []
    rows: list[dict[str, Any]] = []
    row_count: int = 0
    execution_ms: float = 0
    governed_metric: str | None = None
    governed_metric_display_name: str | None = None
    governed_metric_expression: str | None = None
    governed_base_dataset: str | None = None
    unit_format: str | None = None
    connector_type: str | None = None
    connector_name: str | None = None
    connector_id: str | None = None
    truncated: bool = False


class Timings(StrictModel):
    context_ms: float = 0
    planning_ms: float = 0
    validation_ms: float = 0
    query_ms: float = 0
    datasource_ms: float = 0
    analysis_ms: float = 0
    total_ms: float = 0


class LlmUsage(StrictModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    llm_calls: int = 0


class SemanticRuntimeMeta(StrictModel):
    mode: str
    deployment_id: str | None = None
    semantic_version_id: str | None = None
    registry_version_number: int | None = None
    artifact_checksum: str | None = None
    health: str | None = None


class ClarificationOption(StrictModel):
    type: ChatContextSourceType
    id: str
    name: str


class AskDataClarification(StrictModel):
    reason: str
    message: str
    options: list[ClarificationOption] = []


class ModelResolutionMeta(StrictModel):
    capability: str | None = None
    assignment_source: str | None = None
    provider_type: str | None = None
    model_key: str | None = None
    registry_model_id: str | None = None


class AskDataResponse(StrictModel):
    request_id: str
    session_id: str
    status: Status
    provider: str
    model: str
    strategy: Strategy
    answer: AnalysisOutput
    data: QueryData
    chart_spec: ChartSpec | None
    timings: Timings
    retry_count: int = 0
    usage: LlmUsage | None = None
    governed_sql: str | None = None
    route: ResponseRoute | None = None
    grounding: GroundingLevel | None = None
    citations: list[CitationRecord] | None = None
    retrieval: RagRetrievalMeta | None = None
    semantic_runtime: SemanticRuntimeMeta | None = None
    model_resolution: ModelResolutionMeta | None = None
    context_mode: ContextMode | None = None
    clarification: AskDataClarification | None = None
    presentation_tier: PresentationTier | None = None
