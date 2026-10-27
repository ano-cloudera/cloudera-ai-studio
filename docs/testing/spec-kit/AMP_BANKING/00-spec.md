# Spec — Cloudera AI Studio AMP (Golden Banking)

**ID:** AMP-BANKING-SPEC-1.0  
**Scope:** Governed Ask Data, semantic publish, accelerator demo profile  
**Out of scope:** Multi-workspace UI, full UC lineage, CAI artifact packaging

## Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| R-01 | User can ask banking questions **without `@`** when one published model or pinned model is configured | P0 |
| R-02 | Multi-turn follow-up reuses **last governed metric** (amount → channel breakdown → highest channel) | P0 |
| R-03 | Metric clarification shows **clickable chips** with DB metric UUIDs | P0 |
| R-04 | Analysis Workspace shows **Governed definition** (metric, entity, expression) from OSSIE | P0 |
| R-05 | Publish embeds **certified golden questions** from workspace starters | P0 |
| R-06 | AMP readiness gate + scripted UAT evidence | P0 |
| R-07 | Executive presentation (tier1 narrative, heuristic workspace) | P1 |
| R-08 | Browse published metrics (semantic catalog API + Ask Data panel) | P1 |
| R-09 | Answer quality feedback (thumbs → usage events) | P1 |
| R-10 | Genie-style space instructions (`instruction_prompt_key`) | P1 |
| R-11 | Databricks Ontology / Ranger demo narrative (documentation) | P1 |

## Post-AMP (not in this release)

| Tier | Examples |
|------|----------|
| **P2** | LiteLLM proxy + gateway guardrails, full automated UAT sign-off, production deploy checklist |
| **P3** | Multi-workspace UI, UC lineage sync, live Ranger row-filter demo |

## Traceability

See [traceability.md](./traceability.md).
