# Deployment layout

## Application source (repo root)

| Path | What it is |
|------|------------|
| [`backend/`](../backend/) | **FastAPI** application source (`app.main:app`) |
| [`frontend/`](../frontend/) | **Next.js** application source |

These are the only **`backend/`** and **`frontend/`** code trees. Everything under `deployment/` is packaging, env profiles, and CAI launchers.

## This folder (`deployment/`)

| Path | Purpose |
|------|---------|
| [`profiles/`](profiles/) | Env templates (local, CAI, sim) |
| [`specs/`](specs/) | CAI Application specs (ports, health, NFS) — not duplicate app code |
| [`cai/`](cai/) | Cloudera AI **Application entry scripts** + manifest |
| [`amp/`](amp/) | Accelerator packaging pointers |

## CAI launchers (not app source)

Each CAI Application runs a small Python launcher that starts the real app from repo root:

| CAI app | Launcher script | Starts |
|---------|-----------------|--------|
| Studio Backend | [`cai/launchers/studio-backend/app.py`](cai/launchers/studio-backend/app.py) | `backend/` uvicorn |
| Studio Frontend | [`cai/launchers/studio-frontend/app.py`](cai/launchers/studio-frontend/app.py) | `frontend/` `npm run start` |
| Studio Qdrant | [`cai/launchers/studio-qdrant/app.py`](cai/launchers/studio-qdrant/app.py) | Qdrant binary + optional UI |
| Studio vLLM | [`cai/launchers/studio-vllm/app.py`](cai/launchers/studio-vllm/app.py) | vLLM OpenAI server |

Env examples: [`cai/env/`](cai/env/) · Manifest: [`cai/manifests/applications.yaml`](cai/manifests/applications.yaml)

Runbook: [docs/deployment/CAI_4_APP_DEPLOY_RUNBOOK.md](../docs/deployment/CAI_4_APP_DEPLOY_RUNBOOK.md)
