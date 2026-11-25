"""Register the model served by the Anywhere vLLM Application in Settings -> AI Models, through the Backend's own API.

Called by scripts/amp/llm.py after the Application runs. Safe to run again: the provider and the model are found by their key and
updated, never duplicated. A capability that already has a model assigned (a model the person chose) is left alone; only the
capabilities with nothing assigned get this model.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

PROVIDER_KEY = "anywhere-vllm"
MODEL_KEY = "anywhere-vllm-chat"
CAPABILITIES = ("CHAT_DEFAULT", "ASK_DATA", "RAG_GENERATION", "SKILLS")


class RegistryError(Exception):
    pass


def make_call(base_url: str, opener=urllib.request.urlopen, timeout: float = 90):
    """A function (method, path, body) -> dict that talks to the Backend (base_url holds its secret path)."""

    def call(method: str, path: str, body: dict | None = None) -> dict:
        req = urllib.request.Request(
            f"{base_url.rstrip('/')}{path}",
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with opener(req, timeout=timeout) as response:  # noqa: S310 - operator-configured workspace URL
                return json.loads(response.read().decode() or "{}")
        except urllib.error.HTTPError as exc:
            raise RegistryError(f"{method} {path} returned HTTP {exc.code}: {exc.read().decode(errors='replace')[:300]}") from None
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RegistryError(f"{method} {path} failed: {type(exc).__name__}") from None

    return call


def ensure_provider(call, *, base_url: str, secret_ref: str) -> dict:
    config = {"guided_json": True, "disable_thinking": True}  # a JSON schema in every request; no think block before the answer
    found = next((p for p in call("GET", "/api/v1/ai/providers").get("providers", []) if p.get("key") == PROVIDER_KEY), None)
    if found:
        patch = {"base_url": base_url, "secret_ref": secret_ref, "enabled": True, "config_json": {**(found.get("config_json") or {}), **config}}
        return call("PATCH", f"/api/v1/ai/providers/{found['id']}", patch)["provider"]
    body = {"name": "Anywhere vLLM", "key": PROVIDER_KEY, "provider_type": "OPENAI_COMPATIBLE", "base_url": base_url,
            "secret_ref": secret_ref, "enabled": True, "config_json": config}
    return call("POST", "/api/v1/ai/providers", body)["provider"]


def ensure_model(call, provider_id: str, *, name: str, served_name: str, context_window: int | None) -> dict:
    fields = {"name": name, "model_id": served_name, "model_type": "CHAT", "enabled": True, "context_window": context_window,
              "supports_streaming": True, "supports_json_mode": True}
    fields = {k: v for k, v in fields.items() if v is not None}
    found = next((m for m in call("GET", "/api/v1/ai/models").get("models", []) if m.get("key") == MODEL_KEY), None)
    if found:
        return call("PATCH", f"/api/v1/ai/models/{found['id']}", fields)["model"]
    return call("POST", "/api/v1/ai/models", {"provider_id": provider_id, "key": MODEL_KEY, **fields})["model"]


def assign_unassigned(call, model_id: str) -> list[str]:
    """Give this model every capability that has no explicit assignment yet; returns the capabilities it was given."""
    current = {a.get("capability"): a for a in call("GET", "/api/v1/ai/assignments").get("assignments", [])}
    given = []
    for capability in CAPABILITIES:
        existing = current.get(capability) or {}
        if existing.get("source") in ("PROJECT", "WORKSPACE") and existing.get("model_id"):
            continue  # a model the person chose stays
        call("PUT", f"/api/v1/ai/assignments/{capability}", {"model_id": model_id, "enabled": True})
        given.append(capability)
    return given


def register(call, *, base_url: str, name: str, served_name: str, context_window: int | None, secret_ref: str = "env://VLLM_API_KEY") -> dict:
    provider = ensure_provider(call, base_url=base_url, secret_ref=secret_ref)
    model = ensure_model(call, provider["id"], name=name, served_name=served_name, context_window=context_window)
    given = assign_unassigned(call, model["id"])
    try:
        status = call("POST", f"/api/v1/ai/models/{model['id']}/test", {}).get("status") or call("GET", f"/api/v1/ai/models/{model['id']}")["model"].get("status")
    except RegistryError as exc:
        status = f"test failed: {exc}"
    return {"provider_id": provider["id"], "model_id": model["id"], "assigned": given, "status": status}
