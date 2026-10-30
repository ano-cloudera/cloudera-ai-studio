"""URL defaults for the AMP-created Applications.

The AMP starts three Applications with fixed subdomains (`<prefix>-qdrant`, `<prefix>-backend`,
`<prefix>-frontend`), so each launcher can work out the others' URLs from CDSW_DOMAIN. Values set on the
Application (or project) always win; nothing happens outside Cloudera AI (no CDSW_DOMAIN).
"""
from __future__ import annotations

from collections.abc import Mapping


def app_url(name: str, env: Mapping[str, str]) -> str | None:
    domain = env.get("CDSW_DOMAIN", "").strip()
    if not domain:
        return None
    prefix = env.get("AMP_SUBDOMAIN_PREFIX", "").strip() or "anywhere"
    return f"https://{prefix}-{name}.{domain}"


def with_amp_defaults(env: Mapping[str, str], app: str) -> dict[str, str]:
    """Return a copy of env with the cross-Application URLs filled in for `app` ("backend" or "frontend")."""
    out = dict(env)
    if app == "backend":
        qdrant, frontend = app_url("qdrant", env), app_url("frontend", env)
        if qdrant and not out.get("QDRANT_URL"):
            out["QDRANT_URL"] = f"{qdrant}:443"  # keep :443, qdrant-client otherwise falls back to 6333
        if frontend and not out.get("CORS_ORIGINS"):
            out["CORS_ORIGINS"] = frontend
    elif app == "frontend":
        backend = app_url("backend", env)
        if backend and not out.get("BACKEND_API_URL"):
            out["BACKEND_API_URL"] = backend
    return out
