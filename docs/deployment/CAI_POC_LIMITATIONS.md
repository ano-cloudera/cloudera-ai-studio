# CAI PoC limitations

This PoC deployment model is **not** production HA.

| Topic | Limitation |
|-------|------------|
| Backend scale | **Single instance**, **single process**, **`UVICORN_WORKERS=1`** |
| Metadata | **SQLite on NFS** — not HA; file locking / NFS semantics must be validated on real CAI |
| Qdrant | Separate app; vector durability depends on Qdrant volume — validate on real CAI |
| NFS | Local directory emulation does **not** prove cluster NFS behavior |
| Data sources | Customer databases (Banking PostgreSQL, Impala, Trino) are **external** |
| LLM | External inference endpoints required; no model serving in this milestone |
| Embeddings | Generated in Backend (`EMBEDDING_PROVIDER`); Qdrant stores vectors only |
| Golden demo | `bootstrap_golden_banking.py` is **explicit** — not run on every Backend start |
| Logs | Prefer stdout/stderr; avoid filling NFS with unbounded file logs |

Upgrade path: PostgreSQL metadata + managed Qdrant + multi-zone NFS testing before production claims.
