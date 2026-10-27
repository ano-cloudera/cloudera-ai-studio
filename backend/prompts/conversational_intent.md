Classify whether the user's message should be handled as **conversational** (no Impala / no governed KPI query) in TEMPO Ask Data.

Set `is_conversational=true` when the user mainly wants:
- Greetings or small talk (halo, selamat pagi, apa kabar).
- What the assistant can do / example questions / capability overview for management.
- **Conceptual domain explanation** without asking for numbers, rankings, or a query (e.g. difference between sell-in Tempo vs sell-out Alfamart).

Set `is_conversational=false` when the user wants **analytics**: counts, totals, top/ranking, comparisons with data, trends, "berapa", "tampilkan", "hitung", "urutkan", "bandingkan", specific materials/branches/periods with measurable answers—even if the wording mentions "beda/perbedaan" but still asks for quantified comparison.

Set `attach_domain_catalog=true` only when `is_conversational=true` AND the user would benefit from a **first-turn style bullet list** of governed domains (generic hello or "what can you answer?"). Set `false` when the user already narrowed a topic (e.g. only stock examples), asks follow-up in an ongoing chat without repeating capability overview, or asks a focused conceptual question (sell-in vs sell-out definitions).

Respond with JSON only matching the schema.
