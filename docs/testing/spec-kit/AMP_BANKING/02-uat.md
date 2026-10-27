# UAT — Golden Banking AMP (Spec Kit)

**Actors:** SE / product owner  
**Session:** Fresh browser chat session after bootstrap

## UAT scenarios

| ID | Steps | Acceptance |
|----|-------|------------|
| UAT-1 | Open Ask Data, **no `@`**, ask “What is the total transaction amount?” | Single KPI ~3.8B; governed SQL uses SUM(amount) |
| UAT-2 | Same session: “Break it down by channel.” | Bar/table by channel; Branch highest ~872M |
| UAT-3 | Same session: “Which channel had the highest value?” | Branch; consistent with UAT-2 |
| UAT-4 | Settings → pin Banking model + auto-attach ON; new session, repeat UAT-1 | Same without manual `@` |
| UAT-5 | Open Analysis Workspace → Summary | **Governed definition** block visible on tier-3 turn |
| UAT-6 | Ask ambiguous metric (if configured) | Clarification **chips**; pick one → prior question resolves |
| UAT-7 | “Write Python for machine learning” | UNSUPPORTED / guardrail |
| UAT-8 | Knowledge question (no semantic) | RAG answer with sources |

## Automated UAT (LLM required)

```bash
python3 scripts/demo/banking_uat_english_memory_3q.py
python3 scripts/demo/banking_robustness_10q.py
```

Pass: `ok: true` in evidence JSON.

## Sign-off

| Role | Name | Date | Evidence path |
|------|------|------|---------------|
| SE | | | `banking-uat-english-memory-3q.json` |
| PM | | | `readiness-gate.json` |
