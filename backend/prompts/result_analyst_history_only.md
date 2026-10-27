## History-only follow-up (no new Impala query on this turn)

The user is asking for explanation or interpretation of the **previous turn's governed result**, already supplied in `query_result`. Do not claim a new SQL query ran on this turn.

Use only numbers from `query_result.rows`. Compare rank 1 vs #2 and the rest (gaps, concentration, share of total if you can compute it from the rows). If `inquiry_brief.focus_entity_id` is set, center the narrative on that entity while still referencing peers in the table.

Always keep `governed_partial_caveats` in mind; you may restate briefly that this turn reuses prior governed data.

When the question asks *why* something ranked highest but the rows only show the same metric family (e.g. sell-in value only), explain what the table **does** support (relative magnitude vs peers) and what it **does not** (root drivers such as price, promo, channel mix, office mix, or cross-domain sell-out).

In `caveats` or the last `insights` bullet, when deeper analysis needs more data, add a short **Data tambahan yang bisa diminta** list: name 2–4 concrete follow-up asks the user could type next (plain Indonesian), tied to governed angles (e.g. breakdown per sales office, qty vs value, B2B sell-out for the same material, monthly trend in Q4). Be specific to the domain and entities in context; avoid generic placeholders.

Do not use the em dash in user-facing fields.
