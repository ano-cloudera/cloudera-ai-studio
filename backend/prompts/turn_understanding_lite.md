TEMPO Ask Data Q4 2024 — classify this turn only (no follow-up binding).

JSON schema fields: `is_conversational`, `attach_domain_catalog`, `pipeline_question`, optional short `rationale`.

- Conversational: greetings, capability overview, conceptual sell-in vs sell-out (no numbers/SQL).
- Analytic: anything asking for data, rankings, totals, comparisons.
- `pipeline_question`: usually echo the user text unchanged.
- `attach_domain_catalog`: true only for generic hello / "what can I ask?" on a broad first message.

When `session.last_metric` is present, treat the turn as a continuation of the prior governed query (e.g. "per bulan", "pertanyaan tadi"). Rewrite `pipeline_question` into an explicit Q4 analytic question for that metric family; keep `is_conversational=false`.
