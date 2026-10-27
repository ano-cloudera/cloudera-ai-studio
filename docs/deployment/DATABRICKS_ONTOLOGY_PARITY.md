# Databricks Ontology / Genie parity (1-pager)

Cloudera AI Studio Ask Data targets the same **buyer story** as Databricks **Unity Catalog + Metric Views / Ontology + Genie spaces**: business users ask in natural language; answers come from **governed definitions**, not ad-hoc SQL invention.

## Capability map

| Databricks concept | CAI Studio equivalent | Notes |
|------------------|----------------------|--------|
| **Ontology / semantic layer** | Published **semantic model** (metrics, dimensions, joins) | Banking demo: `retail_banking_analytics` |
| **Genie space** | Implicit **default project** + workspace **Ask Data settings** | Pin model, auto-attach, space instructions |
| **Space instructions** | `instruction_prompt_key` on workspace settings | Resolved prompt injected into analyst step |
| **Certified / example questions** | `golden_questions.yaml` on publish + starters | AMP preset + capability catalog |
| **Browse metrics** | `GET /api/v1/ask-data/semantic-catalog` + sidebar panel | Pinned or sole published model |
| **Answer feedback** | `POST /api/v1/ask-data/feedback` → `usage_events` | Thumbs on response footer |
| **Multi-turn** | Session registry follow-up in `context.py` | Amount → channel → max channel |
| **Knowledge alongside metrics** | `@` library chips + RAG | Golden Banking PDFs |
| **Row-level security** | Connector + **Ranger** (deployment) | See `RANGER_ROW_FILTER_DEMO.md` |

## Intentional gaps (POC)

- No multi-workspace Genie UI; single `default` workspace.
- No Databricks-native metric store sync; OSS semantic runtime + Postgres metadata.
- Genie “conversation repair” UX differs; we use clarification chips + governed definition panel.

## Demo script (3 turns)

1. *What is the total transaction amount?* — single KPI, governed metric.
2. *Break down by channel.* — session follow-up, same amount metric + channel dimension.
3. *Which channel is highest?* — comparative narrative on prior result.

## References

- [AMP_ACCELERATOR_PLAYBOOK.md](./AMP_ACCELERATOR_PLAYBOOK.md)
- Spec Kit UAT: `docs/testing/spec-kit/AMP_BANKING/02-uat.md`
