# AMP vertical swap checklist

Use this when replacing **Golden Banking** with another industry while keeping the same **Cloudera AI Studio AMP** mechanics (governed Ask Data + Knowledge + presentation preset).

## Swap these assets

| # | Asset | Banking reference | Your vertical |
|---|--------|-------------------|---------------|
| 1 | Connector + schema | `banking_demo` PostgreSQL | Your warehouse / lakehouse tables |
| 2 | Semantic model YAML + publish | `retail_banking_analytics` | Your model key + metrics |
| 3 | Bootstrap script | `bootstrap_golden_banking.py` | Clone or parameterize (`bootstrap_<vertical>.py`) |
| 4 | Knowledge libraries | Retail Banking Knowledge + PDFs | Your policy / product docs |
| 5 | Preset JSON | `accelerator-demo-presentation.json` | Starters, `instruction_prompt_key`, `hero_semantic_model_key` |
| 6 | Env template | `accelerator.env.example` | Connection strings, embedding provider |
| 7 | UAT / evidence scripts | `banking_uat_*.py` | Same flow, new questions + model key |
| 8 | Spec Kit annex | `AMP_BANKING/` | Copy pattern or add `AMP_<VERTICAL>/` |

## After bootstrap (every env)

```bash
python3 scripts/demo/apply_accelerator_demo_profile.py
# optional: --preset config/examples/accelerator-demo-<vertical>.json
python3 scripts/demo/run_amp_accelerator_readiness.py
```

Confirm Settings (workspace):

- `auto_attach_semantic_model`: **true**
- `default_semantic_model_id`: set by profile script (hero pin)
- Starters match governed questions for your domain

## Demo script (generic 5 minutes)

1. **No `@`** — hero KPI from pinned semantic (multi-turn breakdown + memory).
2. **Optional** — semantic publish / browse metrics panel.
3. **`@` Knowledge library** — document Q&A with sources.
4. **Remove `@` library** — ask hero KPI again (back to governed).
5. **Guardrail** — unsupported intent (e.g. arbitrary code generation).

## Do not assume

- RAG without `@` library or file chip.
- Auto-pick among multiple published models without pin.
- Per-project Ask Data settings (workspace-level only today).

See [AMP_MULTI_CONTEXT_POLICY.md](./AMP_MULTI_CONTEXT_POLICY.md).
