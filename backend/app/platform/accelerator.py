from __future__ import annotations

ACCELERATOR_VERSION = "1.0.0-m6"

FEATURE_PROFILES = frozenset(
    {
        "ASK_DATA_ONLY",
        "RAG_ONLY",
        "ASK_DATA_AND_RAG",
        "FULL_ACCELERATOR",
    }
)


def normalize_feature_profile(raw: str) -> str:
    value = (raw or "FULL_ACCELERATOR").strip().upper()
    if value not in FEATURE_PROFILES:
        return "FULL_ACCELERATOR"
    return value


def rag_enabled_for_profile(profile: str) -> bool:
    return profile in {"RAG_ONLY", "ASK_DATA_AND_RAG", "FULL_ACCELERATOR"}


def ask_data_enabled_for_profile(profile: str) -> bool:
    return profile in {"ASK_DATA_ONLY", "ASK_DATA_AND_RAG", "FULL_ACCELERATOR"}
