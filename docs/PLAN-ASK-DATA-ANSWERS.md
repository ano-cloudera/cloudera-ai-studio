# Plan: better Ask Data answers

Reference: Databricks Genie agents (docs.databricks.com/aws/en/genie-agents/concepts). Genie lets the model write SQL and
then checks it. Studio does the opposite: the model picks governed metrics and the compiler writes the SQL. We keep that,
and borrow what Genie does around it: say how an answer was reached, carry business knowledge per model, test against known
answers, and verify before answering.

## Where we stand against Genie

| Genie concept | Studio today | Gap |
|---|---|---|
| Knowledge store (descriptions, synonyms, joins) | Semantic model: metrics, dimensions, synonyms, governed joins | Fine |
| Instructions (business rules, terms, date formats) | One global prompt (`ask_data.system`) | Not per model |
| Example SQL / trusted assets | Governed metrics are the trusted assets | No example questions per model |
| Benchmarks | `expected_answers.py` and `retrieval_eval.json` run from the CLI | No in-app benchmark |
| Clarifying questions | Metric and dimension clarification chips | Asks when it could answer (orders per month) |
| Inspect (verify the SQL) | `intent_satisfaction.py` checks period, dimension and concept | Only some checks, no retry |
| Agent mode (sub-tasks, report with citations) | Drill-across and comparisons, deterministic; Knowledge is separate | No planner for open questions, no data plus document answers |
| Shows the query and assumptions | SQL panel, "Data source" note | No plain-language "how this was calculated" that does not depend on the model |

## Status

| Phase | State | Where |
|---|---|---|
| 0 | Done | `comparisons.py`, `context.py` (month grain, yearless periods, compare with overall) |
| 1 | Done | `calculation_note.py`, `CalculationNoteBlock.tsx` |
| 2 | Done | Semantic Layer > Answer quality (instructions, examples); instructions reach the analyst |
| 3 | Done | Same tab: expected values, Run benchmark, run history per published version |
| 4 | Done, shows and discloses | `verification.py`: period, monthly split, percentage range, row limit. Warnings reach the analyst and the calculation note. No automatic re-run |
| 5 | Done | `agent_mode.py`: planner, steps through the normal pipeline, one report. `AGENT_MODE_ENABLED=false` turns it off; any failure falls back to the normal answer |

## Phases

| Phase | What | Result for the user | Effort |
|---|---|---|---|
| 0. Fix what the tests found | Month grain: find a month dimension by name pattern (`*_month`), add `order_month` and `ship_month` to the sample data and Trino tables. "Compare X to the overall rate" returns X, overall and difference. A period range without a year uses the latest year in the data instead of being ignored | "Orders per month", "Compare X to overall", "March-May vs June-August" all answer | 1 day |
| 1. Explain every answer | Build a "How this was calculated" block from the plan, not from the model: metric and formula, filters, period, breakdown, source table, comparison used. Show it under the answer, with the SQL behind a toggle. Keeps the `ask_data.system` prompt for tone only | Same explanation for every model, nothing invented | 1 to 2 days |
| 2. Instructions and examples per model | Semantic model gets an Instructions field (terms, rules, fiscal calendar, default period) and a list of example questions that map to a metric and breakdown. Both go into the context sent to the model and into matching | Domain knowledge lives with the model, not in one global prompt | 2 days |
| 3. In-app benchmarks | New tab in Semantic Layer: question, expected value, tolerance. Run all against the published model, show pass or fail and the score per version. Seed with the fulfillment answers | Know whether a new version made answers better or worse before publishing | 2 days |
| 4. Verify before answering | Extend `intent_satisfaction`: the period named in the question is in the filter, the breakdown asked for is in the result, ranking has an order, percentages stay between 0 and 100. On a miss, retry once with the missing constraint, otherwise say what could not be answered | Fewer confident wrong answers | 2 to 3 days |
| 5. Agent mode for open questions | A planner (LLM limited to governed metrics, dimensions and Knowledge libraries) splits a question into steps, runs each through the existing compilers, then writes a short report with citations. Example: "Why is Kalimantan Timur late?" runs by carrier, by month, the policy lookup and a combined summary | Answers that combine data and documents | 4 to 5 days |

## Order and decision points
1. Phase 0 now, because three of the five test questions failed on it.
2. Phase 1 next. It is what makes answers look like Genie's and it needs no new model feature.
3. Phases 2 and 3 together, so benchmarks can prove the instructions help.
4. Phases 4 and 5 last. Phase 5 depends on 1, 3 and 4 to stay trustworthy.

Not copied from Genie: free-form SQL generation by the model. Governed compilation is what keeps numbers identical across
models, so the gap to Genie is in explanation, knowledge and verification, not in query generation.

Thinking or reasoning modes are not part of the plan. They differ per model, add latency, and do not fix formatting or
missing context.

## Understanding stage (Genie / Cortex Analyst style)

Ask Data stays one application and one governed pipeline. What was missing is a tolerant understanding stage in front of
the compiler, so free wording, other languages and typos still end in the same governed numbers.

```
question -> 1 understand (LLM, structured) -> 2 resolve (code, against real values) -> 3 compile (governed)
         -> 4 verify (everything the question names is in the query) -> answer + How this was calculated
```

| Step | State | Where |
|---|---|---|
| 4. Verify: months named without a year must be a date filter | Done | `verification.py` |
| 2. Resolve: misspelt dimension values (applied from 0.85 with a 0.08 margin, otherwise asked back) | Done | `value_filters.py` (`fuzzy_matches`, `resolve_value_matches`), caveats in `workflow.py` |
| 1. Understand: "between X and Y" and "month X with month Y" as two periods, through a structured LLM call with the regex as fallback | Next | `comparisons.py` |
| Feed every failed phrasing into Answer quality | Ongoing | Semantic Layer > Answer quality |
