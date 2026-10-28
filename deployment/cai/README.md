# Cloudera AI Application launchers

These folders are **not** duplicate backend/frontend apps. Each `launchers/studio-*/app.py` is the CAI Application entry cell that starts the real service from the repo root.

| Launcher | Starts |
|----------|--------|
| `launchers/studio-backend/` | [`backend/`](../../backend/) FastAPI |
| `launchers/studio-frontend/` | [`frontend/`](../../frontend/) Next.js |
| `launchers/studio-qdrant/` | Qdrant process + optional `dashboard.py` UI |
| `launchers/studio-vllm/` | vLLM OpenAI API |

See [../README.md](../README.md) for the full deployment map.
