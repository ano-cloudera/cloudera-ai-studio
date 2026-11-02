"""Create or update the Anywhere AI Studio Applications through the Cloudera AI API v2.

Runs as an AMP Job (and can be re-run after a `git pull` to redeploy). It reads
deployment/cai/manifests/applications.yaml, forwards the project's environment variables to each Application,
builds the Frontend, creates or updates each Application, restarts it, and waits until it is running.

Needs the variables Cloudera AI sets in every Session and Job: CDSW_DOMAIN, CDSW_PROJECT_ID, CDSW_APIV2_KEY
(CML_API_KEY works as a fallback). Values are never printed, only variable names.

Usage:
  python scripts/amp/deploy.py --check            # read-only: prove the API key and list Applications
  python scripts/amp/deploy.py --dry-run          # show the plan (names only)
  python scripts/amp/deploy.py [--only backend] [--skip-build] [--timeout 900]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(os.environ.get("STUDIO_REPO_ROOT") or Path(__file__).resolve().parents[2])
MANIFEST = ROOT / "deployment" / "cai" / "manifests" / "applications.yaml"


def _load_amp_defaults():
    path = ROOT / "deployment" / "cai" / "amp_defaults.py"
    spec = importlib.util.spec_from_file_location("amp_defaults", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ApiError(RuntimeError):
    pass


class Cml:
    """Minimal CAI API v2 client (standard library only)."""

    def __init__(self, domain: str, project_id: str, token: str, opener=urllib.request.urlopen):
        self.base = f"https://{domain}/api/v2"
        self.project_id = project_id
        self.token = token
        self._open = opener

    def request(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            f"{self.base}{path}",
            data=data,
            method=method,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with self._open(req, timeout=60) as response:  # noqa: S310 - operator-configured workspace URL
                raw = response.read().decode() or "{}"
        except urllib.error.HTTPError as exc:
            raise ApiError(f"{method} {path} returned HTTP {exc.code}: {exc.read().decode(errors='replace')[:300]}") from None
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ApiError(f"{method} {path} failed: {type(exc).__name__}") from None
        return json.loads(raw)

    def list_applications(self) -> list[dict]:
        apps: list[dict] = []
        token = ""
        while True:
            query = f"?page_size=100{'&page_token=' + token if token else ''}"
            page = self.request("GET", f"/projects/{self.project_id}/applications{query}")
            apps += page.get("applications") or []
            token = page.get("next_page_token") or ""
            if not token:
                return apps

    def project_variables(self) -> dict:
        raw = self.request("GET", f"/projects/{self.project_id}").get("environment") or "{}"
        return json.loads(raw) if isinstance(raw, str) else raw

    def set_project_variables(self, variables: dict[str, str]) -> dict:
        return self.request("PATCH", f"/projects/{self.project_id}", {"environment": json.dumps(variables)})

    def non_string_project_variables(self) -> list[str]:
        """Names (never values) of project variables that are not plain strings; the API rejects those on Applications."""
        return sorted(name for name, value in self.project_variables().items() if not isinstance(value, str))

    def detect_runtime(self) -> str:
        """Runtime image of this project's jobs: the AMP's own jobs run on the runtime the workspace chose."""
        jobs = self.request("GET", f"/projects/{self.project_id}/jobs?page_size=100").get("jobs") or []
        return next((str(j["runtime_identifier"]) for j in jobs if j.get("runtime_identifier")), "")

    def create_application(self, payload: dict) -> dict:
        return self.request("POST", f"/projects/{self.project_id}/applications", payload)

    def update_application(self, app_id: str, payload: dict) -> dict:
        return self.request("PATCH", f"/projects/{self.project_id}/applications/{app_id}", payload)

    def restart_application(self, app_id: str) -> dict:
        return self.request("POST", f"/projects/{self.project_id}/applications/{app_id}:restart", {})

    def get_application(self, app_id: str) -> dict:
        return self.request("GET", f"/projects/{self.project_id}/applications/{app_id}")


def load_manifest(path: Path = MANIFEST) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def build_plan(manifest: dict, env: dict[str, str], only: str | None = None) -> list[dict]:
    amp = _load_amp_defaults()
    prefix = env.get("AMP_SUBDOMAIN_PREFIX", "").strip() or manifest.get("subdomain_prefix", "anywhere")
    derive_env = {**env, "AMP_SUBDOMAIN_PREFIX": prefix}
    extra = [name.strip() for name in env.get("AMP_FORWARD_ENV", "").split(",") if name.strip()]
    plan = []
    for app in manifest["applications"]:
        flag = env.get(app.get("enabled_env", ""), "").strip().lower() in ("1", "true", "yes")
        if app.get("enabled", True) is False and not flag and only != app["key"]:
            continue
        if only and app["key"] != only:
            continue
        environment = {**(manifest.get("shared_environment") or {}), **(app.get("environment") or {})}
        derived = amp.with_amp_defaults(derive_env, app["key"]) if app["key"] in ("backend", "frontend") else derive_env
        for name in ("QDRANT_URL", "CORS_ORIGINS", "BACKEND_API_URL"):
            if app["key"] in ("backend", "frontend") and derived.get(name):
                environment[name] = derived[name]  # an explicit project value wins inside with_amp_defaults
        for name in [*(app.get("forward_env") or []), *(extra if app["key"] == "backend" else [])]:
            if env.get(name):
                environment[name] = env[name]
        if app["key"] == "vllm" and not environment.get("MODEL_PATH") and env.get("VLLM_MODEL_ID"):
            environment["MODEL_PATH"] = f"/home/cdsw/models/{env['VLLM_MODEL_ID'].rsplit('/', 1)[-1]}"
        res = app.get("resources") or {}
        key = app["key"].upper()

        def sized(var: str, default, cast):
            raw = env.get(f"AMP_{key}_{var}", "").strip()
            return cast(raw) if raw else default

        plan.append(
            {
                "key": app["key"],
                "name": app["name"],
                "description": app.get("description", ""),
                "subdomain": f"{prefix}-{app['subdomain']}",
                "script": app["script"],
                "cpu": sized("CPU", res.get("cpu", 1), float),
                "memory": sized("MEMORY_GB", res.get("memory_gb", 1), float),
                "nvidia_gpu": sized("GPU", res.get("nvidia_gpu", 0), int),
                "environment": {k: str(v) for k, v in environment.items()},
                "build": bool(app.get("build")),
                "health_path": app.get("health_path", "/"),
                "runtime_id": env.get(app.get("runtime_env", ""), "").strip(),
                "startup_timeout_s": float(app.get("startup_timeout_s", 0) or 0),
            }
        )
    return plan


def payload_for(item: dict, runtime_id: str = "") -> dict:
    payload = {
        "name": item["name"],
        "description": item["description"],
        "subdomain": item["subdomain"],
        "script": item["script"],
        "cpu": item["cpu"],
        "memory": item["memory"],
        "nvidia_gpu": item["nvidia_gpu"],
        "environment": item["environment"],
        "bypass_authentication": False,
    }
    if runtime_id:
        payload["runtime_identifier"] = runtime_id
    return payload


def build_frontend(item: dict, env: dict[str, str]) -> None:
    frontend = ROOT / "frontend"
    node_home = item["environment"].get("NODE_HOME", "")
    build_env = {**env, **item["environment"]}
    if node_home:
        build_env["PATH"] = f"{node_home}/bin{os.pathsep}{env.get('PATH', '')}"
    if not (frontend / "node_modules" / ".bin" / "next").is_file():
        subprocess.run(["npm", "ci"], cwd=frontend, env=build_env, check=True)
    subprocess.run(["npm", "run", "build"], cwd=frontend, env=build_env, check=True)


def is_running(app: dict) -> bool:
    return "RUNNING" in str(app.get("status", "")).upper()


def wait_running(client: Cml, app_id: str, timeout: float, poll: float = 10.0, sleep=time.sleep) -> dict:
    deadline = time.monotonic() + timeout
    app: dict = {}
    while time.monotonic() < deadline:
        app = client.get_application(app_id)
        if is_running(app):
            return app
        if any(word in str(app.get("status", "")).upper() for word in ("FAIL", "ERROR", "STOPPED")):
            raise ApiError(f"Application {app.get('name')} is {app.get('status')}; read its logs in the workspace.")
        sleep(poll)
    raise ApiError(f"Application {app.get('name')} was not running after {int(timeout)} s (status {app.get('status')}).")


def deploy(client: Cml, plan: list[dict], env: dict[str, str], *, skip_build: bool, timeout: float, log=print, sleep=time.sleep) -> None:
    existing = {a.get("subdomain"): a for a in client.list_applications()}
    default_runtime = env.get("AMP_RUNTIME_ID", "")
    if not default_runtime:
        default_runtime = client.detect_runtime()
        log(f"Runtime: {default_runtime or 'not detected (set AMP_RUNTIME_ID if the workspace asks for a runtime image)'}")
    for item in plan:
        runtime_id = item.get("runtime_id") or default_runtime
        log(f"== {item['name']} ({item['subdomain']})")
        if item["nvidia_gpu"] and not item.get("runtime_id"):
            log("   needs a GPU: set AMP_VLLM_RUNTIME_ID to a GPU-enabled runtime if the workspace rejects this Application")
        if item["build"] and not skip_build:
            log("   building the Frontend (several minutes)")
            build_frontend(item, env)
        found = existing.get(item["subdomain"])
        if found:
            client.update_application(found["id"], payload_for(item, runtime_id))
            client.restart_application(found["id"])
            app_id, action = found["id"], "updated and restarted"
        else:
            app_id, action = client.create_application({**payload_for(item, runtime_id), "project_id": client.project_id})["id"], "created"
        wait_running(client, app_id, max(timeout, item.get("startup_timeout_s", 0)), sleep=sleep)
        log(f"   {action}; running at https://{item['subdomain']}.{env['CDSW_DOMAIN']}")
        if item["key"] == "vllm":
            log(f"   register it in Settings -> AI Models as an OpenAI-compatible provider: base URL https://{item['subdomain']}.{env['CDSW_DOMAIN']}/v1")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--timeout", type=float, default=900.0)
    args, _ = parser.parse_known_args(argv)  # the IPython kernel that runs CAI jobs adds '-f <kernel.json>' to argv
    env = dict(os.environ)
    plan = build_plan(load_manifest(), env, args.only)
    if args.dry_run:
        for item in plan:
            print(f"{item['name']}: https://{item['subdomain']}.<domain>  script={item['script']}  cpu={item['cpu']} memory={item['memory']}GB")
            print(f"   environment variables: {', '.join(sorted(item['environment']))}")
        return 0
    missing = [n for n in ("CDSW_DOMAIN", "CDSW_PROJECT_ID") if not env.get(n)]
    token = env.get("CDSW_APIV2_KEY") or env.get("CML_API_KEY")
    if missing or not token:
        print(f"Missing {', '.join(missing + ([] if token else ['CDSW_APIV2_KEY']))}. Run this inside a Cloudera AI Session or Job.", file=sys.stderr)
        return 2
    client = Cml(env["CDSW_DOMAIN"], env["CDSW_PROJECT_ID"], token)
    try:
        if args.check:
            apps = client.list_applications()
            print(f"API reachable; {len(apps)} Application(s) in the project: {', '.join(sorted(a.get('subdomain', '?') for a in apps)) or 'none'}")
            return 0
        deploy(client, plan, env, skip_build=args.skip_build, timeout=args.timeout)
    except (ApiError, subprocess.CalledProcessError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        if "environment" in str(exc):
            try:
                bad = client.non_string_project_variables()
            except Exception as lookup:  # noqa: BLE001 - diagnosis only
                print(f"Could not inspect the project variables: {type(lookup).__name__}", file=sys.stderr)
            else:
                print(f"Project variables that are not plain strings: {', '.join(bad) or 'none found'}", file=sys.stderr)
                if bad:
                    print("Fix: in a Session run: python scripts/amp/set_env.py (it asks for them again), then run this job again.", file=sys.stderr)
        return 1
    print("All Applications are running.")
    return 0


if __name__ == "__main__":
    # CAI runs job scripts through IPython, which reports even SystemExit(0) as a failed job: exit only on failure.
    code = main(sys.argv[1:])
    if code:
        sys.exit(code)
