from __future__ import annotations

import os
from typing import Protocol, runtime_checkable


@runtime_checkable
class SecretProvider(Protocol):
    def get_secret(self, key: str) -> str: ...


class EnvSecretProvider:
    """Pilot implementation — reads from process environment."""

    def get_secret(self, key: str) -> str:
        return (os.environ.get(key) or "").strip()
