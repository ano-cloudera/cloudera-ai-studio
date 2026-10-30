from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[2] / "deployment" / "cai" / "infisical.py"
_spec = importlib.util.spec_from_file_location("cai_infisical", _PATH)
infisical = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(infisical)

CONFIG = {
    "INFISICAL_URL": "https://infisical.example/",
    "INFISICAL_CLIENT_ID": "id",
    "INFISICAL_CLIENT_SECRET": "secret",
    "INFISICAL_PROJECT_ID": "proj",
}


def _fake(calls, secrets):
    def request(url, *, body=None, token=None):
        calls.append((url, body, token))
        if "universal-auth" in url:
            return {"accessToken": "tok"}
        return {"secrets": secrets}

    return request


def test_without_configuration_the_environment_is_untouched(monkeypatch) -> None:
    monkeypatch.setattr(infisical, "_request", lambda *a, **k: pytest.fail("no network call expected"))
    assert infisical.with_infisical({"A": "1"}) == {"A": "1"}


def test_secrets_fill_missing_variables_and_keep_existing_ones(monkeypatch) -> None:
    calls: list = []
    monkeypatch.setattr(
        infisical,
        "_request",
        _fake(calls, [{"secretKey": "GEMINI_API_KEY", "secretValue": "g"}, {"secretKey": "TRINO_PASSWORD", "secretValue": "new"}]),
    )
    logs: list[str] = []
    out = infisical.with_infisical({**CONFIG, "TRINO_PASSWORD": "kept"}, log=logs.append)
    assert out["GEMINI_API_KEY"] == "g"
    assert out["TRINO_PASSWORD"] == "kept"
    assert calls[0][0] == "https://infisical.example/api/v1/auth/universal-auth/login"
    assert calls[1][2] == "tok" and "environment=prod" in calls[1][0]
    assert not any(value in line for line in logs for value in ("kept", "new"))  # values are never logged
    assert "GEMINI_API_KEY" in logs[0]


def test_override_lets_infisical_win(monkeypatch) -> None:
    monkeypatch.setattr(infisical, "_request", _fake([], [{"secretKey": "TRINO_PASSWORD", "secretValue": "new"}]))
    out = infisical.with_infisical({**CONFIG, "TRINO_PASSWORD": "old", "INFISICAL_OVERRIDE": "1"}, log=lambda _: None)
    assert out["TRINO_PASSWORD"] == "new"


def test_unreachable_infisical_warns_and_continues_unless_required(monkeypatch) -> None:
    def boom(*a, **k):
        raise infisical.InfisicalError("Infisical is not reachable: URLError")

    monkeypatch.setattr(infisical, "_request", boom)
    logs: list[str] = []
    assert infisical.with_infisical({**CONFIG, "A": "1"}, log=logs.append)["A"] == "1"
    assert logs and logs[0].startswith("WARNING")
    with pytest.raises(infisical.InfisicalError):
        infisical.with_infisical({**CONFIG, "INFISICAL_REQUIRED": "1"}, log=lambda _: None)
