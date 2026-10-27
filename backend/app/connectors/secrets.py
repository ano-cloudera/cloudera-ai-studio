from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod

from app.connectors.errors import ConnectorError

_ENV_REF = re.compile(r"^env://([A-Za-z_][A-Za-z0-9_]*)$")


class SecretProvider(ABC):
    @abstractmethod
    def get_secret(self, ref: str) -> str:
        ...

    def has_secret(self, ref: str | None) -> bool:
        if not ref:
            return False
        try:
            self.get_secret(ref)
            return True
        except ConnectorError:
            return False


class EnvironmentSecretProvider(SecretProvider):
    def get_secret(self, ref: str) -> str:
        match = _ENV_REF.match((ref or "").strip())
        if not match:
            raise ConnectorError("INVALID_SECRET_REF", "Secret reference must use env://VAR_NAME", 400)
        var = match.group(1)
        value = os.environ.get(var)
        if value is None or value == "":
            raise ConnectorError("SECRET_NOT_FOUND", f"Environment secret not configured for {var}", 422)
        return value


def mask_secret_ref(ref: str | None) -> str | None:
    if not ref:
        return None
    match = _ENV_REF.match(ref.strip())
    if match:
        return f"env://{match.group(1)}"
    return "masked://***"
