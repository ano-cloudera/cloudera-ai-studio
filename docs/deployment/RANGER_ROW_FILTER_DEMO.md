# Ranger row-filter demo (accelerator narrative)

For enterprise demos, pair **governed Ask Data** with **Apache Ranger** row-level filters on the warehouse/Impala layer so the same semantic question returns **only rows the user may see**.

## Story for SEs

1. **Semantic layer** defines *what* “transaction amount” means (one metric, one SQL template).
2. **Ranger** defines *who* sees which rows (e.g. region, business unit, PII scope).
3. **Ask Data** never bypasses Ranger: execution goes through the configured connector with the end-user or service identity Ranger expects.

## Demo setup (conceptual)

| Step | Action |
|------|--------|
| 1 | Deploy Impala/Trino (or Postgres for lab) with Ranger policies on `banking_demo.fact_*` |
| 2 | Register connector in CAI with credentials subject to Ranger |
| 3 | Publish semantic model pointing at filtered tables/views |
| 4 | Run the same question as **User A** vs **User B**; totals differ only because of Ranger, not because the LLM changed SQL semantics |

## What we show in AMP (without live Ranger)

- **Governed definition** panel: metric key, dimensions, SQL fingerprint.
- **Trust line**: verified metric / governed strategy in response metadata.
- **Documentation**: this page + parity doc linking Ranger as the production control plane.

## Customer talking points

- Ontology answers are **auditable** (definition + query artifact).
- Authorization stays in **Ranger + IAM**, not in prompt instructions.
- CAI is complementary to Databricks Genie: same NL front door, Cloudera-native governance stack.

## Related

- [DATABRICKS_ONTOLOGY_PARITY.md](./DATABRICKS_ONTOLOGY_PARITY.md)
- Golden Banking data: `docs/demo/GOLDEN_BANKING_DATASET.md`
