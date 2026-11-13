# Handoff: response UI and the agent (for Codex)

Written for: a coding agent (Codex) continuing the work on the chat response UI and the agentic answers, with the owner of the repo reviewing. State as of 2026-11-13, branch `main`, everything pushed up to `e4c7558` except the commits listed under "Not yet pushed" (none at the time of writing; check `git log origin/main..HEAD`).

## 1. What this product is

Anywhere AI Studio is a governed analytics app that ships as a Cloudera AI AMP. Ask Data answers questions over a semantic model; an agent investigates when a question needs more than one figure. The fuel distribution sample (`samples/fuel_distribution/`) is a **temporary demo** for a customer meeting around 2026-11-18. The product stays general: nothing outside `samples/` may name the demo or fuel data (see `docs/PLAN-AMP.md` and the project memory).

Repo rules that the owner enforces:
- Work only in this repo (`cloudera-ai-studio`). Do not touch `anywhere-ai-studio`.
- UI text in English. The answer text follows the language of the question (Indonesian for the demo).
- Cloudera identity colours: Electric Indigo `#5351F6` for data, Orange `#FF5A14` for emphasis, navy `#13003D` for headings. Tokens live in `frontend/tailwind.config.js` (`cloudera.*`) and CSS variables in `frontend/src/index.css`.
- Anti-slop rules (`anti-slop/` folder and the antislop skill): no decorative gradients, glow, glass, stock badges or "AI" styling. The owner said explicitly: "jangan terlihat AI". Audit notes are in `anti-slop/audit-001-*.md` and `audit-002-*.md`.
- Do not commit or push unless the owner asks. Commit messages end with a Co-Authored-By line.
- Demo-specific data stays out of `app/`, prompts and manifests.

## 2. Architecture you need

- **Ask Data pipeline**: `backend/app/services/chat.py` (`ChatService`) → `_prepare_turn` (reads the turn with the LLM: `app/ask_data/conversation.py`, `TurnReading` with `kind` data / chat / analysis, `standalone_question`, `uses_previous`) → governed workflow in `backend/app/graph/workflow.py` (LangGraph: understand, resolve, plan, validate, execute, `analyze_result`, judge).
- **Answer writer (governed)**: `analyze_result` in `workflow.py` sends `user_payload` to the LLM with `backend/prompts/result_analyst.md`. Figures are checked afterwards by `app/ask_data/answer_checks.py` (`computed_figures`, `figures_outside`, `review_answer`). Code computes ratios, gaps and above/below lists; the LLM must quote them, not compute them.
- **Agent**: `backend/app/ask_data/agent_mode.py` (`AskDataAgent`, `_read`, `_stream_tools`, `_run_step`) and `backend/app/ask_data/agent_tools.py` (tools `query_metric`, `compare`, `search_documents`, clarification; `step_card`, `finding`, `write_report`). Prompts: `agent_tools.md` (the loop), `agent_tool_report.md` (the final report), `agent_planner.md` and `agent_refine.md` (plan mode). Feature flags: `AGENT_LOOP` (default `tools`), `AGENT_ANSWERS_ALL` (default off; routes every data question to the agent; not yet judged on CAI).
- **Routing of follow-ups**: prompt `backend/prompts/conversation_rewrite.md`, rule 8 (after an investigation, "kalau Sulawesi?" continues it). A state-based routing rule was tried and removed (commit `1f40241`) because it sent "per bulan?" to the agent too.
- **Presentation tiers**: `frontend/src/lib/presentationTier.ts` (tier 1 lookup, 2 light analysis, 3 full analysis). Tier 3 with a report puts the chart in the chat (`chatDocumentSplit` in `frontend/src/views/AskDataPage.tsx`, up to `INLINE_CHART_MAX_ROWS = 15`) and the detail in the panel.
- **Analysis panel**: `frontend/src/components/AnalysisReportPanel.tsx`, `ReportDocumentSection.tsx` (tabs: Summary, Map, Table, Query, Sources, Checks). Opens only when the user clicks the Analysis Workspace card (`reportPanelOpenRef` in `AskDataPage.tsx`).
- **Single figure**: `frontend/src/components/FigureCallout.tsx` (`singleFigure`). Shows one number large with `metric_target` and how far it is from it; red or green only when `metric_better` is declared.
- **Checks**: `frontend/src/components/AgentSteps.tsx` (`AgentSteps` renders cards; it lives in the panel's Checks tab now, not in the chat).
- **Home**: `backend/app/home/dashboard.py`, `frontend/src/views/HomePage.tsx`. KPIs only from metrics the model owner marks "Show on Home"; direction and target are declared, never guessed.
- **Usage**: `backend/app/api/usage.py` (`prior_totals`, MTD consistent across endpoints), `frontend/src/views/UsagePage.tsx`.
- **Actions** (MCP actions the agent proposes, run only after a person presses Run): `backend/app/mcp/actions.py`, `action_log.py` (records with `duration_ms` and `request_id`; `delete`), `backend/app/api/v1/mcp.py` (`/actions/run`, `/actions/history`, `/actions/delete`, `/actions/status`), `frontend/src/views/ActionsPage.tsx` (table with search, filter, selection, delete). Operations Desk server (`samples/ops_desk/`) is **off** for the demo.

## 3. Commits since the last handoff point (`896c791`)

| Commit | What |
|---|---|
| `f228d00`, `7cd00d3`, `5c5cd79` | Product logo changed, cropped, reverted to the original (`Logo.png`, `branding/anywhere-ai-logo.png`). |
| `431b201` | Panel opens on click only; sidebar title wraps; charts orange again; follow-up after an investigation (prompt). |
| `1f40241` | Backed out the blunt routing rule; prompt rule 8 sharpened. |
| `e0327ac` | English platform labels; checks move into a panel tab; headline same size as body; agent report prompt asks for scannable bodies; chat rail 800px. |
| `bc6a116` | Usage redesigned: change against the period before, shares as bars, audit-002. |
| `9502ab1` | Usage period filter consistent (MTD in all endpoints), stale responses ignored. |
| `c4772d2` | `samples/fuel_distribution/judge_demo.json`: the ten demo questions in order. |
| `c0063d0` | Actions table like Knowledge, delete (one or many), details dialog, `duration_ms`, `request_id`. |
| `e4c7558` | Answer quality: `computed_figures` places every group above/below overall (`above_overall`, `below_overall`); prompts forbid "only/both" claims not in those lists; figure rounding; chart in chat; `FigureCallout`; `metric_target` in `QueryData`; `_titled()` uses "per" for Indonesian. |

## 4. Verification state

- Backend: `cd backend && PYTHONPATH=. python -m pytest tests -q --ignore=tests/test_mcp_chat_e2e.py --ignore=tests/test_mcp_connector.py -p no:cacheprovider` → 607 passed, 88 skipped. The two ignored files need a local Postgres on port 55432 (not running on the author's machine).
- Frontend: `cd frontend && npx vitest run` → 408 passed. `npx next build` passes.
- Judge (answer quality on the rehearsed conversation): last recorded on CAI was 13/16 with failures at #5 (distance), #11 (Kertapati), #15 (summary). Fixes for those are in prompts and **not yet re-judged**. Run `python scripts/judge_answers.py --cases samples/fuel_distribution/judge_demo.json --out /home/cdsw/j_demo.json` on CAI after rebuild.
- **Nothing in section 3 has been looked at in a running browser.** Do not assume the layout is right; check it on CAI or with a dev server.

## 5. Known problems, in priority order

1. **Panel duplicates the chat.** For a breakdown, chat shows answer, chart, meaning and two bullets; the panel's Summary tab repeats the executive summary, key findings and the chart. Proposed fix: Summary in the panel shows only what the chat does not (extra findings beyond two, method, map), the chart in the panel only for more than 15 categories. Table, Query and Checks stay. Not implemented yet; the owner asked for this.
2. **Old answers still wrong.** A screenshot after the last deploy showed "34,5%" and "Jatimbalinus is the only region below overall" (five are below). If this recurs on a fresh answer, check that the new `computed.above_overall` reaches the prompt (`analyze_result` payload and `_allowed_figures`) and that `result_analyst.md` is the one loaded.
3. **Agent answers still long.** Prompt asks for bodies near 150 words and paragraphs of three sentences; not verified on Nemotron.
4. **Favicon.** `frontend/app/icon.png` is an older third logo (blue C with orange bars). The sidebar and tab icon can differ. Owner has not decided: delete it so the favicon follows the configured logo, or replace it.
5. **AGENT_ANSWERS_ALL** is off. Turn it on only after a judge run shows it is at least as good; the owner wants the Genie-like feel, so this is the lever.
6. **Operations Desk** is off for the demo; the Actions menu hides itself when there is no record and no action tool.
7. Test noise: the two Postgres-bound test files fail locally; do not "fix" them by changing the code under test.

## 6. What the owner wants next (verbatim intent)

- Responses that feel like Genie: flexible, comprehensive, short where the question is short, with an analysis and a cause when the question asks "kenapa" or "bantu analisa". Enhance the cards in the chat if they are the problem.
- Follow-up chips after each answer; the first is "why" when one group stands out.
- Keep the UI sober and Cloudera-branded; no decorative AI styling.
- The owner will send the latest updates after this handoff; add them to this file rather than starting a new one.

## 7. Where to start

1. `git pull` and read section 5, item 1.
2. Reproduce on a dev server with the judge file, or ask the owner for a CAI screenshot.
3. Keep changes small; run both test suites before reporting.
