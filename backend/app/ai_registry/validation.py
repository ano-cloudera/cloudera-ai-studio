from __future__ import annotations

import re

from app.ai_registry.errors import AiRegistryError
from app.ai_registry.secrets import SecretResolver, mask_secret_ref
from app.ai_registry.types import CAPABILITIES, CAPABILITY_REQUIRED_MODEL_TYPE, MODEL_TYPES, PROVIDER_TYPES

_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")


def validate_provider_key(key: str) -> None:
    if not _KEY_RE.match(key):
        raise AiRegistryError("INVALID_ASSIGNMENT", "Provider key must be lowercase alphanumeric with underscores", 422)


def validate_model_key(key: str) -> None:
    validate_provider_key(key)


def validate_provider_payload(
    *,
    provider_type: str,
    secret_ref: str | None,
    base_url: str | None,
    secrets: SecretResolver | None = None,
) -> None:
    ptype = provider_type.upper()
    if ptype not in PROVIDER_TYPES:
        raise AiRegistryError("PROVIDER_UNREACHABLE", f"Invalid provider_type: {provider_type}", 422)
    if ptype in {"OPENAI", "GEMINI", "ANTHROPIC"} and not secret_ref:
        raise AiRegistryError("SECRET_NOT_FOUND", f"{ptype} provider requires secret_ref", 422)
    if secret_ref and not mask_secret_ref(secret_ref):
        raise AiRegistryError("INVALID_SECRET_REF", "Secret reference must use env://VAR_NAME", 422)
    _ = secrets  # reserved for optional strict checks in tests
    if ptype == "OPENAI_COMPATIBLE" and not (base_url or "").strip():
        raise AiRegistryError("PROVIDER_UNREACHABLE", "OPENAI_COMPATIBLE requires base_url", 422)


def validate_model_payload(
    *,
    model_type: str,
    model_id: str,
    context_window: int | None,
    max_output_tokens: int | None,
) -> None:
    mtype = model_type.upper()
    if mtype not in MODEL_TYPES:
        raise AiRegistryError("MODEL_INVALID", f"Invalid model_type: {model_type}", 422)
    if not (model_id or "").strip():
        raise AiRegistryError("MODEL_INVALID", "model_id is required", 422)
    for label, value in (("context_window", context_window), ("max_output_tokens", max_output_tokens)):
        if value is not None and value <= 0:
            raise AiRegistryError("MODEL_INVALID", f"{label} must be positive when set", 422)


def validate_assignment(*, capability: str, model_type: str) -> None:
    cap = capability.upper()
    if cap not in CAPABILITIES:
        raise AiRegistryError("INVALID_ASSIGNMENT", f"Unknown capability: {capability}", 422)
    required = CAPABILITY_REQUIRED_MODEL_TYPE[cap]
    if model_type.upper() != required:
        raise AiRegistryError(
            "INVALID_ASSIGNMENT",
            f"Capability {cap} requires model_type {required}, got {model_type}",
            422,
        )
