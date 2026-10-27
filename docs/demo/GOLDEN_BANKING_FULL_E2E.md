# Golden Banking — Full Local E2E Acceptance

Final **local CAI simulation** product acceptance for the Golden Banking demo (no CAI deploy, no AMP).

## Architecture

| Layer | Local binding |
|-------|----------------|
| Frontend | http://127.0.0.1:3001 (`./scripts/dev-frontend.sh`) |
| Backend | http://127.0.0.1:8001 (`./scripts/dev-cai-sim-backend.sh`), `UVICORN_WORKERS=1` |
| Metadata | SQLite `runtime/cai-sim/metadata/studio.db` |
| Documents | `runtime/cai-sim/documents/` |
| Semantic runtime | `runtime/cai-sim/var/semantic-runtime/` |
| Vectors | Qdrant http://127.0.0.1:6333 |
| Structured source | Banking PostgreSQL `banking_demo` (connector `golden_banking_pg`) |

## Golden journey

1. **Data Sources** — Banking PostgreSQL connected; `customers` / `transactions` discovered.
2. **Raw Ask** — `@customers`, `@transactions`, aggregations, multi-table join.
3. **Knowledge** — Retail Banking Knowledge (two PDFs READY).
4. **Knowledge RAG** — `@Retail Banking Knowledge` with citations.
5. **Semantic** — Retail Banking Analytics published/active.
6. **Governed Ask** — `@Retail Banking Analytics` metrics/dimensions/joins on PostgreSQL.
7. **Contrasts** — Raw vs Governed; Knowledge vs Semantic (failed transaction rate).
8. **Prompts / Skills** — Golden E2E prompt + skill (execute via Skills API; Chat does not invoke skills directly).
9. **AI Model Registry** — providers/models/assignments; `env://` secret refs only.
10. **Usage** — `/usage/summary` and `/usage/events`.
11. **Restart** — backend, frontend, full stack; metadata + governed + RAG survive.

## Commands

```bash
# Stack (canonical)
./scripts/dev-cai-sim-backend.sh start
./scripts/dev-frontend.sh start

# Bootstrap (idempotent)
export BANKING_DEMO_PG_PASSWORD=m1pass   # or set in .env
python scripts/demo/bootstrap_golden_banking.py --dry-run
python scripts/demo/bootstrap_golden_banking.py --apply
python scripts/demo/bootstrap_golden_banking.py --validate

# Full E2E gate
python scripts/demo/golden_path_banking_full_e2e_gate.py

# Safe reset (library + connector only; requires confirm)
GOLDEN_RESET_CONFIRM=1 python scripts/demo/reset_golden_banking.py --apply
python scripts/demo/reset_golden_banking.py --dry-run

# Fresh disposable install proof
python scripts/demo/golden_path_banking_fresh_install_bootstrap.py
```

## Evidence

- API: `testing/evidence/golden-path/FULL-E2E/api-e2e-evidence.json`
- Restart: `testing/evidence/golden-path/FULL-E2E/restart-evidence.json`
- Browser: `testing/evidence/golden-path/FULL-E2E/browser/01-…-18-….png`
- Gate report: `testing/evidence/golden-path/FULL-E2E/full-e2e-gate-report.json`

## Intentional demo assets

| Asset | Key / name |
|-------|------------|
| Data Source | Banking PostgreSQL (`golden_banking_pg`) |
| Knowledge | Retail Banking Knowledge |
| Semantic | Retail Banking Analytics (`retail_banking_analytics`) |
| E2E Prompt | Golden Banking Executive Summary (`golden_banking_executive_summary`) |
| E2E Skill | Golden Banking Analyst (`golden_banking_analyst`) |

Active semantic **runtime** follows the latest successful publish recorded in `PHASE3-SEMANTIC/semantic-registration.json`.
