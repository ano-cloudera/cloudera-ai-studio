# Frontend CAI Application — deployment spec (neutral)

> **Superseded for CAI Applications:** the Script field must be a Python entrypoint (`deployment/cai/launchers/studio-*/app.py`), never a `.sh` file. `scripts/cai/start-*.sh` are for local/Session use only. See [CAI_4_APP_DEPLOY_RUNBOOK.md](../../docs/deployment/CAI_4_APP_DEPLOY_RUNBOOK.md).

**Application source code:** repository root [`frontend/`](../../frontend/) (not under `deployment/`).  
**CAI launcher:** [`deployment/cai/launchers/studio-frontend/app.py`](../cai/launchers/studio-frontend/app.py).

| Field | Value |
|-------|--------|
| Runtime | Node.js (LTS), Next.js 15 production server |
| Build | `npm ci && npm run build` (in `frontend/`) |
| Start command | `npm run start` with `PORT`, `HOST=0.0.0.0` |
| Wrapper | `scripts/cai/start-frontend.sh start` |
| Default port | 3000 (`PORT`) |

## Environment

| Variable | Required | Notes |
|----------|----------|--------|
| `BACKEND_API_URL` | Yes | Server-side rewrite target (internal Backend URL) |
| `NEXT_PUBLIC_BACKEND_URL` | Recommended | Client-visible API base |
| `PORT` | No | Listen port |

No direct Qdrant or metadata DB access.

## Health

| Check | Notes |
|-------|--------|
| `GET /` | Liveness — Next.js responds 200 when ready |

No backend call required for basic liveness.

## Dependencies

- Backend reachable from Frontend pod/network at `BACKEND_API_URL`
