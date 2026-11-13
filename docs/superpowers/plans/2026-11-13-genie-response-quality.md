# Genie Response Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove duplicated analysis content and make governed and agent answers concise, numerically grounded, and naturally investigative.

**Architecture:** Keep the chat as the primary narrative and pass its presentation split into the report panel so the panel renders only complementary material. Preserve deterministic computed comparisons at the LLM boundary and tighten prompts where answer shape remains model-controlled.

**Tech Stack:** React, TypeScript, Vitest, Python, pytest, Markdown prompts.

**Spec:** `docs/HANDOFF-CODEX.md` and the user's 2026-11-13 request.

## Global Constraints

- Work only in `cloudera-ai-studio`; do not touch `anywhere-ai-studio`.
- UI copy is English; generated answers follow the question language.
- Use existing Cloudera tokens; add no gradients, glow, glass, or decorative badges.
- Demo-specific content stays under `samples/`.
- Do not commit or push.

## Review Focus

- A tier-3 answer with 15 or fewer categories must show its chart only in chat.
- A tier-3 answer with more than 15 categories must show its chart only in the workspace.
- Summary must omit chat narrative and the first two chat findings while retaining later findings and analysis-only content.
- Every group comparison supplied to the model must include complete above/below lists and stable precision.
- Agent and follow-up prompt changes must preserve language and avoid invented causes.

---

### Task 1: Complementary Analysis Workspace

**Files:**
- Modify: `frontend/src/components/ReportDocumentSection.tsx`
- Modify: `frontend/src/components/AnalysisReportPanel.tsx`
- Modify: `frontend/src/views/AskDataPage.tsx`
- Test: `frontend/src/components/ReportDocumentSection.test.tsx`

- [ ] Write failing tests for short and long category sets and complementary findings.
- [ ] Run the focused tests and verify the expected failures.
- [ ] Pass chat presentation metadata into the panel and render only complementary Summary content.
- [ ] Run focused frontend tests and verify they pass.

### Task 2: Computed Comparison Contract

**Files:**
- Modify: `backend/tests/test_workflow.py`
- Modify: `backend/tests/test_agent_tools.py`
- Modify if needed: `backend/app/graph/workflow.py`
- Modify if needed: `backend/app/ask_data/agent_tools.py`

- [ ] Write failing boundary tests that inspect the real model payload.
- [ ] Verify the tests fail for the missing contract, or record that production already satisfies it.
- [ ] Make the smallest production change needed to preserve complete lists and precision.
- [ ] Run focused backend tests.

### Task 3: Concise Agent Reports and Why-First Follow-ups

**Files:**
- Modify: `backend/prompts/agent_tool_report.md`
- Modify: `backend/prompts/result_analyst.md`
- Test: relevant backend prompt and agent behavior tests.

- [ ] Add behavior-oriented regression coverage where practical.
- [ ] Tighten report structure around a direct opening and roughly 150 words.
- [ ] Require the first follow-up to be a standalone why question whenever a group stands out.
- [ ] Run focused backend tests.

### Task 4: Verification and Visual Check

- [ ] Run the required backend suite.
- [ ] Run the required frontend suite and Next build.
- [ ] Attempt the answer judge and report endpoint limitations exactly.
- [ ] Start the frontend dev server and inspect availability; do not claim layout correctness without a browser or CAI check.
- [ ] Review the final diff for scope, sample leakage, brand tokens, and anti-slop violations.
