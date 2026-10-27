# Golden Path Banking Demo — Knowledge (Phase 2)

Phase 2 adds **Retail Banking Knowledge**: business/policy PDFs that complement Phase 1 PostgreSQL facts. Questions with explicit `@Retail Banking Knowledge` route to **RAG/Knowledge**, not Raw Data or Semantic Layer.

## Library

| Field | Value |
|-------|--------|
| Name | **Retail Banking Knowledge** |
| Description | Business policies, customer segmentation guidance, and transaction definitions for the Golden Banking Demo. |
| Documents | 2 PDFs (see below) |

## Documents

| PDF | Source markdown | Contents |
|-----|-----------------|----------|
| `Retail Banking Transaction Policy.pdf` | `demo/knowledge/transaction-policy.md` | Status definitions (Success/Failed/Pending), channels, transaction types, monitoring notes, **Failed Transaction Rate** rule |
| `Customer Segment and Risk Guide.pdf` | `demo/knowledge/customer-segment-risk-guide.md` | Segments (Retail/Priority/SME), statuses, risk tiers, Priority/High Risk demo definitions |

All text is **synthetic demo content** (not real bank policy).

## Regenerate PDFs (deterministic)

```bash
python scripts/demo/generate_banking_knowledge.py
```

Outputs:

- `demo/knowledge/generated/Retail Banking Transaction Policy.pdf`
- `demo/knowledge/generated/Customer Segment and Risk Guide.pdf`
- `demo/knowledge/generated/manifest.sha256.json`

Requires `fpdf2` (see `backend/requirements.txt`).

## Register library + batch upload (live API)

Backend on **8001**, Qdrant reachable, platform DB up:

```bash
python scripts/demo/generate_banking_knowledge.py
python scripts/demo/register_banking_knowledge.py
```

Recreate only this library (deletes existing **Retail Banking Knowledge** by name, then re-uploads):

```bash
python scripts/demo/register_banking_knowledge.py --recreate
```

Evidence: `testing/evidence/golden-path/PHASE2-KNOWLEDGE/library-registration.json`

Optional API base: `GOLDEN_PATH_API_BASE=http://127.0.0.1:8001`

For local Golden Path PDFs (text-native), set `DOCUMENT_PDF_USE_PYPDF=true` in `.env` so ingestion uses pypdf instead of Docling. Restart the backend after changing it.

## Example questions (explicit context)

Use the Knowledge library in the context picker (e.g. `@Retail Banking Knowledge`).

| Question | Expected source |
|----------|-----------------|
| What does Failed transaction mean? | Transaction Policy |
| How is Failed Transaction Rate defined? | Failed attempts ÷ total attempts (policy) |
| Which transaction channels are defined in the policy? | Mobile Banking, Internet Banking, ATM, Branch, EDC |
| What is a Priority Customer? | Segment guide |
| What are the three customer risk tiers? | Low, Medium, High |
| What does High Risk mean in this demo? | Elevated monitoring (demo classification) |
| How should a high-risk Priority customer with failed transactions be interpreted? | Synthesis from **both** PDFs (no SQL) |

## Routing

| Context | Path | Notes |
|---------|------|--------|
| `@Retail Banking Knowledge` | RAG / Knowledge | `apply_context_sources` → `mode=rag` |
| `@transactions` (Phase 1 table) | Raw Data (`RAW_TABLE`) | PostgreSQL, not document retrieval |
| Knowledge + table together | **422** `mixed_context_unsupported` | No silent hybrid in this phase |

## Citations & Sources drawer

RAG answers should include **citations** (filename, snippet). Use **View sources** in chat for the Sources drawer (inline RAG; does not open Analysis Workspace for ordinary policy Q&A).

## Automated checks

```bash
PYTHONPATH=backend GOLDEN_BANKING_RUN_INTEGRATION=1 pytest backend/tests/test_golden_banking_phase2_knowledge.py -q
python scripts/demo/phase2_api_rag_evidence.py
python scripts/demo/golden_path_banking_phase2_knowledge_gate.py
```

Phase 1 regression:

```bash
PYTHONPATH=backend GOLDEN_BANKING_RUN_INTEGRATION=1 pytest backend/tests/test_golden_banking_phase1.py -q
```

## Evidence layout

`testing/evidence/golden-path/PHASE2-KNOWLEDGE/`

- `library-registration.json` — live registration
- `api-rag-evidence.json` — retrieval + raw vs knowledge contrast
- `phase2-gate-report.json` — acceptance gate
- `browser-evidence-manifest.json` — UI capture index
