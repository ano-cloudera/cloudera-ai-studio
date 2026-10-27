from __future__ import annotations

import os
import re

from app.ai_registry.errors import AiRegistryError

_ENV_REF = re.compile(r"^env://([A-Za-z_][A-Za-z0-9_]*)$")


class SecretResolver:
    """Resolve secret references (baseline: env://VAR only)."""

    def resolve(self, secret_ref: str) -> str:
        ref = (secret_ref or "").strip()
        match = _ENV_REF.match(ref)
        if not match:
            raise AiRegistryError("INVALID_SECRET_REF", "Secret reference must use env://VAR_NAME", 400)
        var = match.group(1)
        value = os.environ.get(var)
        if value is None or value == "":
            raise AiRegistryError("SECRET_NOT_FOUND", f"Environment secret not configured for {var}", 422)
        return value

    def has_secret(self, secret_ref: str | None) -> bool:
        if not secret_ref:
            return False
        try:
            self.resolve(secret_ref)
            return True
        except AiRegistryError:
            return False


def mask_secret_ref(ref: str | None) -> str | None:
    if not ref:
        return None
    match = _ENV_REF.match(ref.strip())
    if match:
        return f"env://{match.group(1)}"
    return None
