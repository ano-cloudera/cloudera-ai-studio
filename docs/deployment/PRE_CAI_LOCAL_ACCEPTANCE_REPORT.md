# Pre-CAI Local Acceptance Report — Golden Banking Full E2E

## Summary

Local Golden Banking acceptance validates the complete product journey on the **CAI simulation** stack (SQLite metadata, single worker, Qdrant, external Banking PostgreSQL) before any CAI deployment or AMP packaging.

## Architecture validated

- Frontend `:3001` → Backend `:8001` (single process)
- SQLite metadata at `runtime/cai-sim/metadata/studio.db`
- Persistent document + semantic runtime under `runtime/cai-sim/`
- Qdrant `:6333` for Knowledge vectors
- Banking PostgreSQL connector for Raw + Governed structured queries

## Bootstrap & reset

- **Bootstrap:** `scripts/demo/bootstrap_golden_banking.py` (`--dry-run`, `--apply`, `--validate`)
- **Fresh install proof:** `scripts/demo/golden_path_banking_fresh_install_bootstrap.py` → disposable root `runtime/cai-sim-golden-fresh-e2e` on port `8002`
- **Safe reset:** `scripts/demo/reset_golden_banking.py` (library + connector only; non-default)

## Test execution

Gate orchestrator: `scripts/demo/golden_path_banking_full_e2e_gate.py`

Includes Golden Phase 1/2/3 + Phase 3 closure, full backend pytest, frontend Vitest, and production build.

## Browser evidence index

| File | Journey step |
|------|----------------|
| `01-data-sources.png` | Connectors / Banking PostgreSQL |
| `02-raw-single-table.png` | Raw `@customers` |
| `03-raw-aggregation.png` | Raw aggregation by channel |
| `04-raw-multi-table.png` | Raw multi-table join |
| `05-knowledge-library.png` | Knowledge library + PDFs |
| `06-knowledge-rag-citation.png` | RAG answer |
| `07-knowledge-sources.png` | Sources context |
| `08-semantic-model.png` | Semantic layer overview |
| `09-11` | Governed metric / dimension / join |
| `12-13` | Raw vs Governed; Knowledge vs Semantic |
| `14-17` | Prompts, Skills, AI models, Usage |
| `18-chat-history-after-restart.png` | Chat history surface |

## Remaining CAI-specific risks (out of scope for local PASS)

- NFS-backed metadata and multi-worker UVicorn on CAI
- Real CAI Application lifecycle and ingress/TLS
- AMP clean-install on customer clusters
- Production secret management (Vault vs `env://` local refs)
- Horizontal Qdrant / embedding service sizing

## Recommended next milestone

**CAI deployment engineering** — deploy backend + frontend CAI Applications using `deployment/profiles/cai.env`, then **AMP packaging** and clean-install validation.
