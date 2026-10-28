# Qdrant CAI Application — deployment spec (neutral)

**CAI launcher:** [`deployment/cai/launchers/studio-qdrant/app.py`](../cai/launchers/studio-qdrant/app.py) (Qdrant binary + optional UI).

| Field | Value |
|-------|--------|
| Image | Official Qdrant (version pinned in real CAI deploy) |
| Port | 6333 (HTTP API) |
| Storage | Persistent volume at Qdrant `storage_path` (e.g. `/qdrant/storage`) |

## Backend integration

Backend uses:

- `QDRANT_URL` — e.g. `http://qdrant-service:6333`
- `QDRANT_COLLECTION` — default `accelerator_chunks`
- `QDRANT_API_KEY` — optional secret

Embeddings are **not** generated inside Qdrant; Backend embedding provider writes vectors.

## Health (verify on target Qdrant version in real CAI)

| Endpoint | Typical use |
|----------|-------------|
| `GET /healthz` | Liveness/readiness (Qdrant 1.x+) |
| `GET /collections` | Functional probe from Backend |

**DEFERRED_TO_REAL_CAI:** exact health URL semantics must be confirmed against the Qdrant version shipped in CAI.

## PoC sizing (estimate)

| Resource | Recommendation |
|----------|------------------|
| CPU | 1–2 cores |
| RAM | 2–4 GiB (Golden demo + headroom) |
| GPU | None |
| Disk | 5–20 GiB persistent (demo PDFs embedded as vectors) |

## Persistence validation

Local Docker restart test when available; otherwise see `docs/deployment/CAI_REAL_DEPLOYMENT_CHECKLIST.md`.
