# Handoff — Claude (testing, development, CAI deployment)

**Date:** 2026-10-28 (updated ~19:22 UTC+7)  
**Repo:** `cloudera-ai-studio` (standalone AMP / Cloudera AI Studio)  
**Prior agent:** Cursor (MCP UI, env hygiene, hackathon branding, Ask Data stream fix)

---

## Ringkasan (untuk Triano)

- **Produk:** Cloudera AI Studio AMP — governed Ask Data, Knowledge `@`, workspace **MCP** (`@` chip), deploy target **4 CAI apps**.
- **Branch:** `main` — commit **`41b321e`** (MCP + CAI layout + inflight chat + handoff); **belum push** kecuali sudah di-push manual.
- **Stack lokal:** backend **8001**, frontend **3001**, `./scripts/dev-stack.sh`.
- **Env:** [LOCAL_ENV_HYGIENE.md](../deployment/LOCAL_ENV_HYGIENE.md).
- **State:** [PROJECT_STATE.md](../../PROJECT_STATE.md).

---

## What was completed (this sprint)

### MCP (workspace-driven, stdio/SSE)

| Area | Details |
|------|---------|
| Backend | `backend/app/mcp/`, `backend/app/api/v1/mcp.py`, `backend/app/workspace/mcp_settings.py` |
| APIs | `GET/PUT /api/v1/mcp/settings`, `GET /api/v1/mcp/connectors`, `POST /api/v1/mcp/test-connection` |
| Chat | `mode=mcp`, `strategy=mcp`; skips LLM validation on MCP path |
| Frontend | **Settings → MCP** tab (between Features & Advanced), `AskDataMcpSettingsPanel.tsx` |
| UX | **Test connection** + **Save MCP connections** (purple outline button); Brave preset |
| Tests | `backend/tests/test_mcp_connector.py`, `test_mcp_chat_e2e.py`; `SettingsPage.test.tsx` |

### Settings hygiene

- Removed **Demo question bank** (legacy FMCG UAT) from UI; saves always `starter_source=configured`.
- Renamed **Legacy chat fallback** → **Default chat model** (still required when registry has no assignment).

### Deployment docs

- `docs/deployment/CAI_4_APP_DEPLOY_RUNBOOK.md`, `deployment/README.md`, `deployment/cai/launchers/`
- `scripts/demo/verify_pre_deploy.py`

### Ask Data — stream survives tab navigation (2026-10-28)

| Issue | Fix |
|-------|-----|
| User sends chat, switches sidebar tab → API aborted, "Request stopped." | Removed unmount `AbortController` cleanup on `AskDataPage` |
| Implementation | `frontend/src/lib/askDataInflightStream.ts` — global inflight SSE; `startInflightStream` / `subscribeInflightStream` / `abortInflightStream`; persists via `saveSession` |
| Tests | `frontend/src/lib/askDataInflightStream.test.ts`; `AskDataPage.test.tsx` still passes |

**Manual check:** Ask Data → send question → immediately open Settings → wait → return to Ask Data; answer should complete in background.

### Dev / frontend stability

- `scripts/dev-frontend.sh`: `restart-clean`, HTTP 200 health, env load hygiene, avoid `.next` corruption while `next dev` runs
- Hackathon branding: `frontend/src/config/publicBranding.ts`, `PublicBrandingContext.tsx`, `docs/deployment/HACKATHON_TEMP_BRANDING.md`

---

## Hackathon UI branding (2026-10-28)

Temporary **Anywhere AI Studio** via `frontend/.env.local` + `public/branding/anywhere-ai-logo.png`. Revert: [HACKATHON_TEMP_BRANDING.md](../deployment/HACKATHON_TEMP_BRANDING.md).

---

## Pre-handoff test run (2026-10-28 ~18:20 UTC+7)

| Suite | Result |
|-------|--------|
| `verify_pre_deploy.py` | **PASS** (`ok: true`; amp_readiness WARN bootstrap) |
| MCP pytest + ask-data settings | **7 passed** |
| Backend full pytest | **492 passed**, **10 failed**, 85 skipped (see below) |
| Frontend vitest | **246+ passed** (includes `askDataInflightStream.test.ts`); **3 failed** pre-existing (semantic UX mocks; not MCP) |
| `npm run build` | **PASS** (after type fixes: MCP payload, metric authoring, semantic preview) |
| `run_amp_accelerator_readiness.py` | **FAIL** gates: `bootstrap_validate`, `demo_profile_tier1_narrative` (expected until bootstrap + `--apply-profile`) |

**Backend failures (pre-existing, not MCP blockers):** `tests/test_workflow.py` (7), golden banking evidence scripts (3).

**Frontend failures:** `aiRegistryUi.test.ts` (copy mismatch), `semanticLayerPhase2A*.test.tsx` (Edit button → row actions menu mocks).

---

## Verification commands (run first in Claude session)

```bash
cd cloudera-ai-studio
./scripts/dev-backend.sh start
# optional: ./scripts/dev-stack.sh

.venv/bin/python scripts/demo/verify_pre_deploy.py http://127.0.0.1:8001
# Expect: "ok": true (pytest_mcp, mcp_settings_api, mcp_connectors_api, mcp_chat_live)
# amp_readiness may WARN until bootstrap on target

cd backend && ../.venv/bin/python -m pytest tests/test_mcp_connector.py tests/test_mcp_chat_e2e.py -q
cd ../frontend && npm test -- src/views/SettingsPage.test.tsx
```

**MCP manual UI:** Settings → MCP → Add Brave Search preset → Test connection (needs `BRAVE_API_KEY` on backend) → Save → Ask Data `@` → MCP connector.

---

## Git / commit note

**Do not assume remote is up to date.** Large uncommitted diff on `main` includes MCP, deployment folder cleanup, multi-context docs, Ask Data tweaks.

Suggested commit grouping (when user asks):

1. `feat(mcp): workspace settings, test connection, chat path`
2. `feat(settings): MCP tab, starter question hygiene`
3. `docs(deploy): CAI 4-app runbook, env hygiene, handoff`

User preference: **commit only when explicitly requested.**

---

## Known gaps / next work

| Priority | Item |
|----------|------|
| **P0 deploy** | Push branch, CAI 4-app per [CAI_4_APP_DEPLOY_RUNBOOK.md](../deployment/CAI_4_APP_DEPLOY_RUNBOOK.md); NFS + secrets |
| **P0 target** | `bootstrap_golden_banking.py --apply` + `apply_accelerator_demo_profile.py` on Backend session |
| **P1** | Full backend pytest: ~7 failures in `tests/test_workflow.py` (pre-existing mock/registry; not MCP blocker) |
| **P1 UAT** | Fill `docs/testing/spec-kit/AMP_BANKING/02-uat.md` sign-off; optional live scripts |
| **P2 UX** | Surface **Default chat model** outside `<details>` on AI Models tab (recommended, not done) |
| **P2 backend** | Optional: remove `question_bank` API path after migration (UI already gone) |
| **MCP prod** | Brave stdio needs `npx` + network on Backend runtime; SSE alternative if stdio blocked |

---

## Architecture pointers

| Topic | Doc |
|-------|-----|
| Multi-context `@` / pin | [AMP_MULTI_CONTEXT_POLICY.md](../deployment/AMP_MULTI_CONTEXT_POLICY.md) |
| Vertical swap | [AMP_VERTICAL_SWAP_CHECKLIST.md](../deployment/AMP_VERTICAL_SWAP_CHECKLIST.md) |
| Playbook | [AMP_ACCELERATOR_PLAYBOOK.md](../deployment/AMP_ACCELERATOR_PLAYBOOK.md) |
| Chat context | [CHAT_CONTEXT_MODEL.md](../frontend/CHAT_CONTEXT_MODEL.md) |
| Env contract | [CAI_DEPLOYMENT_ENV_CONTRACT.md](../architecture/CAI_DEPLOYMENT_ENV_CONTRACT.md) |

---

## Key file map (quick navigation)

```
backend/app/api/v1/mcp.py
backend/app/mcp/client.py          # probe_mcp_server, invoke_mcp_server
backend/app/mcp/service.py         # run_mcp_turn
backend/app/services/chat.py       # MCP branch
frontend/src/views/settings/AskDataMcpSettingsPanel.tsx
frontend/src/views/SettingsPage.tsx
frontend/src/lib/chatContext.ts
frontend/src/lib/askDataInflightStream.ts
scripts/demo/verify_pre_deploy.py
deployment/cai/launchers/
```

---

## Instructions for Claude

1. Read **PROJECT_STATE.md** and this handoff; confirm `verify_pre_deploy.py` on user's machine.
2. Continue **testing** (UAT checklist, browser MCP, governed + Knowledge + MCP `@` family policy).
3. Continue **development** from gaps table; minimize scope; match existing conventions.
4. **Deployment:** follow 4-app runbook; set `BRAVE_API_KEY`, `DATABASE_URL`, `QDRANT_URL`, CORS, `BACKEND_API_URL`.
5. Communicate with user in **Indonesian** unless they switch to English.
6. Do **not** commit/push unless user asks.

---

## User store / transcript

- Cursor agent transcript (full context): project `agent-transcripts/d1452e33-60d8-4721-812d-67df230fddaf.jsonl`
- Attach this file + `PROJECT_STATE.md` when opening a new Claude session.
