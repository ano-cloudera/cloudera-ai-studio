from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ProviderType = Literal["OPENAI", "GEMINI", "ANTHROPIC", "OPENAI_COMPATIBLE"]
ModelType = Literal["CHAT", "EMBEDDING", "RERANKER"]
Capability = Literal[
    "CHAT_DEFAULT",
    "ASK_DATA",
    "RAG_GENERATION",
    "SKILLS",
    "EMBEDDING",
    "RERANKER",
]
TestStatus = Literal["READY", "FAILED", "NOT_TESTED"]
AssignmentSource = Literal["PROJECT", "WORKSPACE", "LEGACY_FALLBACK"]

PROVIDER_TYPES = frozenset({"OPENAI", "GEMINI", "ANTHROPIC", "OPENAI_COMPATIBLE"})
MODEL_TYPES = frozenset({"CHAT", "EMBEDDING", "RERANKER"})
CAPABILITIES = frozenset(
    {"CHAT_DEFAULT", "ASK_DATA", "RAG_GENERATION", "SKILLS", "EMBEDDING", "RERANKER"}
)

CAPABILITY_REQUIRED_MODEL_TYPE: dict[str, str] = {
    "CHAT_DEFAULT": "CHAT",
    "ASK_DATA": "CHAT",
    "RAG_GENERATION": "CHAT",
    "SKILLS": "CHAT",
    "EMBEDDING": "EMBEDDING",
    "RERANKER": "RERANKER",
}


@dataclass(frozen=True)
class AdapterTestResult:
    status: TestStatus
    latency_ms: float
    error_code: str | None = None
    safe_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
