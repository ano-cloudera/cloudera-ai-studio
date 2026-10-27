# Golden Path Banking Demo — Synthetic Dataset (Phase 1)

Phase 1 proves **Raw Ask Data** against PostgreSQL **before** any Knowledge library or Semantic Layer exists.

## Database target

| Item | Value |
|------|--------|
| Host (local) | `127.0.0.1:55432` |
| Database | `banking_demo` (separate from platform metadata DB `accelerator`) |
| Schema | `banking_demo` |
| Tables | `banking_demo.customers`, `banking_demo.transactions` |
| Credentials | user `m1`, password via `BANKING_DEMO_PG_PASSWORD` (default `m1pass` in local profile) |

Platform metadata (connectors, projects) stays in `accelerator`. Banking facts live only in `banking_demo`.

## Table definitions

### `banking_demo.customers` (~250 rows)

| Column | Type | Notes |
|--------|------|--------|
| `customer_id` | INTEGER PK | |
| `customer_name` | TEXT | Synthetic Indonesian-style names |
| `segment` | TEXT | `Retail`, `Priority`, `SME` |
| `city` | TEXT | Jakarta, Bandung, Surabaya, Medan, Makassar, Yogyakarta |
| `join_date` | DATE | |
| `customer_status` | TEXT | `Active`, `Dormant`, `Closed` |
| `risk_tier` | TEXT | `Low`, `Medium`, `High` |

### `banking_demo.transactions` (~1000 rows)

| Column | Type | Notes |
|--------|------|--------|
| `transaction_id` | INTEGER PK | |
| `customer_id` | INTEGER FK → `customers.customer_id` | No orphans |
| `transaction_date` | DATE | 2026-01-01 … 2026-09-30 |
| `transaction_type` | TEXT | Transfer, Payment, Purchase, Withdrawal, Deposit |
| `channel` | TEXT | Mobile Banking, Internet Banking, ATM, Branch, EDC |
| `merchant_category` | TEXT | Groceries, Dining, Travel, Utilities, Healthcare, Education, Retail |
| `amount` | NUMERIC(18,2) | Always &gt; 0, synthetic IDR |
| `status` | TEXT | Success, Failed, Pending |

## Relationship

- One customer → many transactions via `customer_id`.
- Seed enforces FK integrity and varied volumes per customer, channels, and failure rates.

## Seed / reset commands

From repo root:

```bash
# Plan only (default)
python scripts/demo/seed_banking_postgres.py --dry-run

# Idempotent apply (skips if customers already populated)
python scripts/demo/seed_banking_postgres.py --apply \
  --export-validation testing/evidence/golden-path/banking-data/seed-validation.json

# Drop and re-seed (deterministic seed=42)
python scripts/demo/seed_banking_postgres.py --apply --reset --seed 42 \
  --export-validation testing/evidence/golden-path/banking-data/seed-validation.json
```

Generator module: `scripts/demo/banking_data_generator.py` (fixed seed **42**, reproducible).

## Data Source (canonical API)

```bash
export BANKING_DEMO_PG_PASSWORD=m1pass
export BANKING_CONNECTOR_EVIDENCE=testing/evidence/golden-path/PHASE1/connector-registration.json
python scripts/demo/register_banking_connector.py
```

Creates or updates connector **Banking PostgreSQL** (`golden_banking_pg`) pointing at `banking_demo`.

## Example Raw Ask questions (no semantic layer)

Use **@Table** context in the UI or `context_sources` in API.

| Context | Question |
|---------|----------|
| `@customers` | How many active customers are there? |
| `@transactions` | What is the total transaction amount? |
| `@transactions` | How many failed transactions are there? |
| `@transactions` | Break down transaction amount by channel. |
| `@transactions` (mention **customers** in text for join) | Which customers segment has the highest total transaction amount? |

Responses should show **Raw data** (`context_mode: RAW_TABLE`), not Governed Semantic.

SQL governance: **SELECT/WITH only** (no DML/DDL). Prefer explicit column lists (`COUNT(customer_id)` not `COUNT(*)`).

## Validation evidence

- Row counts and distributions: `testing/evidence/golden-path/banking-data/seed-validation.json`
- Phase 1 gate / browser: `testing/evidence/golden-path/PHASE1/`

## Phase 1 gate script

```bash
python scripts/demo/golden_path_banking_phase1_gate.py
```

Emits `GOLDEN_PATH_BANKING_DEMO_PHASE1_PASS` or `GOLDEN_PATH_BANKING_DEMO_PHASE1_BLOCKED` with blockers.
