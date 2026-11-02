"""Names of the environment variables a Data Source or AI model can point to with `env://NAME`.

Only names are returned, never values. The list is what the Backend can actually read, so it matches the variables
added to the project (the deploy Job copies them to the Backend) and anything named in AMP_FORWARD_ENV.
"""
from __future__ import annotations

import os
import re

from fastapi import APIRouter

router = APIRouter(prefix="/environment", tags=["environment"])

_SECRET_LIKE = re.compile(r"(KEY|PASSWORD|PASSWD|SECRET|TOKEN|CREDENTIAL)", re.I)
# Infrastructure secrets of the platform itself: never offered as a Data Source or model credential.
_INTERNAL = frozenset({"STUDIO_API_TOKEN", "QDRANT_API_KEY", "CDSW_APIV2_KEY", "CML_API_KEY", "DATABASE_URL"})
_SYSTEM_PREFIXES = ("CDSW_", "CML_", "KUBERNETES_", "LC_", "XDG_")


def _kind(name: str) -> str:
    upper = name.upper()
    if upper.endswith(("_API_KEY", "_KEY")) or "API_KEY" in upper:
        return "api_key"
    if "PASSWORD" in upper or "PASSWD" in upper:
        return "password"
    if "TOKEN" in upper:
        return "token"
    return "other"


def environment_references(environ: dict[str, str] | None = None) -> list[dict[str, str]]:
    env = os.environ if environ is None else environ
    forwarded = {n.strip() for n in env.get("AMP_FORWARD_ENV", "").split(",") if n.strip()}
    names = {
        name
        for name, value in env.items()
        if value
        and name not in _INTERNAL
        and not name.startswith(_SYSTEM_PREFIXES)
        and (name in forwarded or _SECRET_LIKE.search(name))
    }
    return [{"name": n, "ref": f"env://{n}", "kind": _kind(n)} for n in sorted(names)]


@router.get("/references")
def list_references() -> dict:
    return {"references": environment_references()}
