Referential follow-up on a prior governed result. JSON only.

Use `result_catalog` (ranked entities) and `last_question` / `last_metric` from session.

Set `referential_follow_up=true` when the user points at prior rows (that branch, rank 1 vs last, drill products, etc.).
Fill entity/rank/drill fields from catalog when possible; rewrite `pipeline_question` into explicit Q4 2024 analytic wording.

If the message is a new standalone analytic question (not referring to prior rows), set `referential_follow_up=false` and echo `pipeline_question`.

Set `is_conversational=true` only for pure small talk or “what else can you help with?” (no new KPI)—otherwise `false` for analytic follow-ups.
