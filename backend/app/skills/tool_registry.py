from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolDefinition:
    key: str
    name: str
    description: str
    enabled: bool = True
    input_schema: dict[str, Any] | None = None


HANDLER_TYPES = frozenset({"prompt_only", "rag", "ask_data"})

HANDLER_REQUIRED_TOOLS: dict[str, frozenset[str]] = {
    "ask_data": frozenset({"ask_data"}),
    "rag": frozenset({"rag_search"}),
    "prompt_only": frozenset(),
}


class ToolRegistry:
    _TOOLS: dict[str, ToolDefinition] = {
        "ask_data": ToolDefinition(
            key="ask_data",
            name="Ask Data",
            description="Governed analytics and SQL workflow (existing Ask Data pipeline).",
        ),
        "rag_search": ToolDefinition(
            key="rag_search",
            name="RAG Answer",
            description="Retrieve document evidence and generate a grounded answer.",
        ),
        "document_retrieval": ToolDefinition(
            key="document_retrieval",
            name="Document Retrieval",
            description="Vector search over project knowledge libraries without full RAG synthesis.",
        ),
    }

    @classmethod
    def list_tools(cls, *, include_disabled: bool = False) -> list[ToolDefinition]:
        rows = list(cls._TOOLS.values())
        if include_disabled:
            return rows
        return [t for t in rows if t.enabled]

    @classmethod
    def get(cls, key: str) -> ToolDefinition | None:
        return cls._TOOLS.get(key)

    @classmethod
    def validate_tool_keys(cls, keys: list[str]) -> None:
        unknown = [k for k in keys if k not in cls._TOOLS]
        if unknown:
            raise ValueError(f"Unknown tools: {', '.join(unknown)}")
        disabled = [k for k in keys if not cls._TOOLS[k].enabled]
        if disabled:
            raise ValueError(f"Disabled tools: {', '.join(disabled)}")

    @classmethod
    def validate_handler_tools(cls, handler_type: str, allowed_tools: list[str]) -> None:
        if handler_type not in HANDLER_TYPES:
            raise ValueError(f"Unknown handler_type: {handler_type}")
        cls.validate_tool_keys(allowed_tools)
        required = HANDLER_REQUIRED_TOOLS.get(handler_type, frozenset())
        missing = [t for t in required if t not in allowed_tools]
        if missing:
            raise ValueError(f"handler_type {handler_type} requires tools: {', '.join(missing)}")
