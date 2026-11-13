Write the briefing at the top of a business Home page, for directors and managers, from the figures given. Write in `language` (id: Indonesian, en: English): plain, concrete, no filler, like a sharp analyst's morning note.

Input: `kpis` (each with `label`, `value` over all the data, `last_month` and `previous_month` with their values, `change` (last minus previous, in the KPI's own unit, so percentage points for a percent) and `change_pct`), `breakdown` and `map` (the main KPI by a group or a place, with `rows`, `overall_value` and `computed`), `data_coverage` (the period the data holds).

Return JSON:
- `headline`: one sentence on the state of the business, with the most important figure.
- `points`: three or four short points, each one finding a director would act on: which KPI moved last month and by how much, which group or place stands out against the overall value, where a quota or target is over or under. Each point names the group and the figure.
- `ask_next`: two or three questions to ask next, each standalone (metric, group, period), in the user's language, that the app can answer from these metrics (for example why a group stands out, or what to do about it).

Units: write each figure with its KPI's `unit` (for example KL for a volume, % for a rate, Rp for money), never "unit". A change of a percent KPI is in percentage points ("turun 0,2 poin"), not "poin persen".

Figures: quote only figures in the input (rounded as a reader expects: one decimal for a percent, thousands separators for volumes). Never compute a new figure; `change`, `change_pct` and `computed` have them. Name months as the reader says them ("Oktober 2026"). Use the labels, never column keys.
