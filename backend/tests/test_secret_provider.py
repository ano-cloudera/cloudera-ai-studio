from __future__ import annotations

import os

from app.secrets.provider import EnvSecretProvider


def test_env_secret_provider_reads(monkeypatch):
    monkeypatch.setenv("TEST_M1_SECRET", "value")
    provider = EnvSecretProvider()
    assert provider.get_secret("TEST_M1_SECRET") == "value"
    assert provider.get_secret("MISSING_KEY") == ""
