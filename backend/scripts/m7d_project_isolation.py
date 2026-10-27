#!/usr/bin/env python3
"""M7D.1 project isolation evidence (API-level)."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid

BASE = os.environ.get("M7D_BASE_URL", "http://127.0.0.1:8001")


def req(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode()
    r = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if body else {},
    )
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        if not raw.strip():
            return e.code, {"detail": str(e)}
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


def main() -> None:
    out: dict[str, object] = {}
    projects = req("GET", "/api/v1/projects")[1]["projects"]
    if len(projects) < 2:
        print(json.dumps({"pass": False, "reason": "need_at_least_two_projects"}))
        return
    proj_a, proj_b = projects[0]["id"], projects[1]["id"]
    ws = projects[0]["workspace_id"]
    out["project_a"] = proj_a
    out["project_b"] = proj_b

    model_id = "e030608f-ffa6-4662-989d-29137eee83f0"
    # Assign ASK_DATA on default project context (API uses default project from deps)
    st, _ = req("PUT", "/api/v1/ai/assignments/ASK_DATA", {"model_id": model_id})
    asn = req("GET", "/api/v1/ai/assignments")[1]
    ask = next(a for a in asn["assignments"] if a["capability"] == "ASK_DATA")
    out["ask_data_assignment_on_default"] = ask

    iso_key = f"m7d.iso.prompt.{uuid.uuid4().hex[:8]}"
    st, pr = req(
        "POST",
        "/api/v1/prompts",
        {
            "name": "M7D Iso A",
            "key": iso_key,
            "scope": "project",
            "workspace_id": ws,
            "project_id": proj_a,
            "initial_content": "CONTENT_A",
        },
    )
    pid_a = pr["prompt"]["id"]
    vid = req("GET", f"/api/v1/prompts/{pid_a}/versions")[1]["versions"][0]["id"]
    req("POST", f"/api/v1/prompts/{pid_a}/versions/{vid}/publish")
    st, pr_b = req(
        "POST",
        "/api/v1/prompts",
        {
            "name": "M7D Iso B",
            "key": iso_key,
            "scope": "project",
            "workspace_id": ws,
            "project_id": proj_b,
            "initial_content": "CONTENT_B",
        },
    )
    pid_b = pr_b["prompt"]["id"]
    vid_b = req("GET", f"/api/v1/prompts/{pid_b}/versions")[1]["versions"][0]["id"]
    req("POST", f"/api/v1/prompts/{pid_b}/versions/{vid_b}/publish")

    ra = req("POST", "/api/v1/prompts/resolve", {"prompt_key": iso_key, "project_id": proj_a})[1]
    rb = req("POST", "/api/v1/prompts/resolve", {"prompt_key": iso_key, "project_id": proj_b})[1]
    out["prompt_isolation"] = ra["content"] == "CONTENT_A" and rb["content"] == "CONTENT_B"

    lib_a_name = f"M7D-Iso-A-{uuid.uuid4().hex[:6]}"
    st, la = req("POST", "/api/v1/libraries", {"name": lib_a_name})
    lib_a = la["library"]["id"]
    out["library_a"] = lib_a
    # Project B cannot see A's library in list? Libraries are workspace scoped - check names unique
    libs = req("GET", "/api/v1/libraries")[1]["libraries"]
    out["library_created_visible"] = any(l["id"] == lib_a for l in libs)

    req("DELETE", f"/api/v1/libraries/{lib_a}")
    req("DELETE", f"/api/v1/prompts/{pid_a}")
    req("DELETE", f"/api/v1/prompts/{pid_b}")
    req("DELETE", "/api/v1/ai/assignments/ASK_DATA")

    out["pass"] = out.get("prompt_isolation") is True
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
