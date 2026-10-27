from __future__ import annotations

# Stable keys mapped to file fallbacks in FilePromptSource
ASK_DATA_SYSTEM = "ask_data.system"
RAG_SYSTEM = "rag.system"
RAG_INSUFFICIENT_EVIDENCE = "rag.insufficient_evidence"

KNOWN_PROMPT_KEYS = frozenset({ASK_DATA_SYSTEM, RAG_SYSTEM, RAG_INSUFFICIENT_EVIDENCE})
