"""Optional Infisical secret loading for CAI launchers (standard library only, no CLI to install).

Off unless INFISICAL_URL, INFISICAL_CLIENT_ID, INFISICAL_CLIENT_SECRET and INFISICAL_PROJECT_ID are all set.
Secrets are merged into the launcher's environment, so the app keeps reading them as plain environment
variables (including the env://VAR references stored in the UI). Values are never logged.

Variables:
  INFISICAL_URL            e.g. https://app.infisical.com or your self-hosted URL
  INFISICAL_CLIENT_ID      Machine Identity (Universal Auth) client id
  INFISICAL_CLIENT_SECRET  Machine Identity client secret
  INFISICAL_PROJECT_ID     Project (workspace) id
  INFISICAL_ENV            environment slug, default "prod"
  INFISICAL_SECRET_PATH    folder, default "/"
  INFISICAL_OVERRIDE       "1" lets Infisical replace variables already set on the Application (default: keep them)
  INFISICAL_REQUIRED       "1" stops the launcher when Infisical cannot be read (default: warn and continue)
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping

_REQUIRED = ("INFISICAL_URL", "INFISICAL_CLIENT_ID", "INFISICAL_CLIENT_SECRET", "INFISICAL_PROJECT_ID")
_TIMEOUT = 15.0


class InfisicalError(RuntimeError):
    pass


def _request(url: str, *, body: dict | None = None, token: str | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:  # noqa: S310 - URL is operator-configured
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise InfisicalError(f"Infisical returned HTTP {exc.code} for {urllib.parse.urlsplit(url).path}") from None
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise InfisicalError(f"Infisical is not reachable: {type(exc).__name__}") from None


def fetch_secrets(env: Mapping[str, str]) -> dict[str, str]:
    base = env["INFISICAL_URL"].strip().rstrip("/")
    login = _request(
        f"{base}/api/v1/auth/universal-auth/login",
        body={"clientId": env["INFISICAL_CLIENT_ID"], "clientSecret": env["INFISICAL_CLIENT_SECRET"]},
    )
    token = login.get("accessToken")
    if not token:
        raise InfisicalError("Infisical login returned no access token")
    query = urllib.parse.urlencode(
        {
            "workspaceId": env["INFISICAL_PROJECT_ID"],
            "projectId": env["INFISICAL_PROJECT_ID"],
            "environment": env.get("INFISICAL_ENV", "prod"),
            "secretPath": env.get("INFISICAL_SECRET_PATH", "/"),
            "expandSecretReferences": "true",
        }
    )
    payload = _request(f"{base}/api/v3/secrets/raw?{query}", token=token)
    return {
        str(item["secretKey"]): str(item.get("secretValue", ""))
        for item in payload.get("secrets") or []
        if item.get("secretKey")
    }


def with_infisical(env: Mapping[str, str], log=print) -> dict[str, str]:
    """Return a copy of env with Infisical secrets merged in. A no-op when Infisical is not configured."""
    merged = dict(env)
    if not all(env.get(name, "").strip() for name in _REQUIRED):
        return merged
    try:
        secrets = fetch_secrets(env)
    except InfisicalError as exc:
        if env.get("INFISICAL_REQUIRED", "") == "1":
            raise
        log(f"WARNING: {exc}; continuing with the Application environment only")
        return merged
    override = env.get("INFISICAL_OVERRIDE", "") == "1"
    applied = [name for name, value in secrets.items() if value and (override or not merged.get(name))]
    for name in applied:
        merged[name] = secrets[name]
    log(f"Infisical: loaded {len(applied)} of {len(secrets)} secrets (names: {', '.join(sorted(applied)) or 'none'})")
    return merged
