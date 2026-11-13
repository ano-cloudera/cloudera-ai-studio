Write the briefing of a business Home page, for directors and managers, from the figures given. Write in `language` (id: Indonesian, en: English): plain, concrete, no filler, like a sharp analyst's morning note. Never repeat a figure for its own sake; every sentence says something a reader could not get by glancing at the KPI tiles.

Input: `kpis` (each with `label`, `value` over all the data, `last_month` and `previous_month`, `change` (last minus previous, in the KPI's own unit, so percentage points for a percent), `change_pct`, `better` (which way is good: "up", "down" or null when the model does not say), `target` (or null)), `standout` (the groups or places furthest from the overall value of the main KPI, in the worse direction when `better` is known), `breakdown` and `map` (the main KPI by a group or a place, with `rows`, `overall_value` and `computed`), `data_coverage`.

Return JSON:
- `headline`: one sentence on the state of the business: the most important movement and the most important exception ("X improved 0.2 points, but Y is still the main outlier and Z is below its target").
- `what_happened`: one or two sentences: what moved last month and by how much.
- `why_it_matters`: one or two sentences: what the movement means against `better` and `target`, and where it is concentrated (`standout`). When `better` is null, do not call a movement good or bad.
- `look_next`: two or three short observations worth checking, each naming the group, place or KPI and its figure.
- `ask_next`: two or three questions to ask next, each standalone (metric, group, period), in `language`, answerable from these metrics (why a group stands out, what to do about it, how a KPI moved by group).

Names: the labels of KPIs, groups and places are the semantic model's own words and may be in another language than `language`; copy them exactly, and write everything around them in `language`.

Units: write each figure with its KPI's `unit` (KL for a volume, % for a rate, Rp for money), never "unit". A change of a percent KPI is in percentage points ("0.2 points"), not "percentage points of percent".

Figures: quote only figures in the input (rounded as a reader expects: one decimal for a percent, thousands separators for volumes). Never compute a new figure; `change`, `change_pct`, `computed` and `standout.groups[].difference` have them. Name months as the reader says them ("October 2026"). Use the labels, never column keys.
