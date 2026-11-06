# Test plan: fulfillment and delivery sample

Written for whoever tests a fresh deployment. Set up the data first ([samples/fulfillment/README.md](../samples/fulfillment/README.md)).
Every expected number comes from the CSVs: run `python samples/fulfillment/expected_answers.py` to recompute them. Fill the **Result** column
with Pass, Fail or Partial, and write the time you ran it. Rows marked *known limit* are not implemented yet: run them to record the
behavior, and do not count them as failures.

| # | Area | Test | Expected | Result |
|---|---|---|---|---|
| P1 | Platform | Open the Frontend | Badge **Platform Ready** | |
| P2 | Platform | Open `<backend-url>/version` without the secret | 404 (the Backend is not open) | |
| P3 | Platform | Open `<qdrant-url>/collections` without a key | 401 or 403 | |
| P4 | Platform | Settings -> AI Models: add Gemini (`env://GEMINI_API_KEY`), assign it to Ask Data, Knowledge and MCP | Model listed as available | |
| P5 | Platform | Data Sources -> add Trino (pick `TRINO_PASSWORD` in the **Secret reference** list), **Test connection**, browse the tables | Connection OK; `fulfillment_orders`, `delivery_shipments`, `v_fulfillment_delivery` visible | |
| P5b | Platform | Edit the Data Source (Config), change a field, **Save changes** | Goes back to the Overview, shows "Changes saved" and runs the connection test by itself | |
| P5c | Platform | Browse Data -> **Refresh** (click it twice quickly) | The button says "Refreshing…" and is disabled until done; the open table's columns are reloaded; no duplicate calls | |
| P5d | Platform | Settings -> AI Models -> add a provider; open **Secret reference** | A list of the key variables the Backend can read (for example `GEMINI_API_KEY`); "Other" lets you type a name | |
| P5e | Platform | Settings -> **Advanced** -> **How answers are shown**: pick a preset, change a choice, watch **What you will see**, then **Save for this workspace** | The preview changes at once; the card shows Custom when no preset matches; Save keeps it; Reset to defaults returns to Demo | |
| P5f | Platform | Settings -> **General** -> Ask Data: edit the starter questions, then open **Default semantic model** | Only the published models are listed, plus Automatic and None; a warning appears when none or several are published and Automatic is chosen; **Save Ask Data settings** keeps it | |
| P5g | Platform | Settings -> AI Models, bottom: **Retrieval pipeline** | A read-only card: embedding model with its dimension (bge-m3, 1024) and the reranker (Not used, or bge when enabled); no assignment lists | |
| P6 | Platform | Run the **Deploy applications** Job again with no change | Finishes, all Applications Running (about 3 min, plus about 30 s per Application update) | |
| S1 | Semantic | Create one model with the 3 entities from [SEMANTIC-MODEL.md](../samples/fulfillment/SEMANTIC-MODEL.md), **Publish** | Published; the metrics appear under "Browse published metrics" | |
| S2 | Semantic | Open **Semantic Layer** | A table in the same style as Data Sources (purple header, **Actions** column with **Open** and **⋯**): the name as words (no underscores), status (Published vN, Draft vN), data models, metrics, dimensions, last modified, and **Default for Ask Data** on the pinned one. Clicking a row opens the model; **← All semantic models** comes back | |
| S2b | Semantic | In the list, open the **⋯** menu of a published model and choose **Set as default** | A green notice; the **Default for Ask Data** badge moves to that row; Settings -> General -> Ask Data shows the same model; the button is not offered for unpublished models or the current default | |
| S2c | Semantic | **Create semantic model**, type `fulfillment_delivery` as the name and click out of the field | The name becomes **Fulfillment Delivery** and a line under it shows `Key: fulfillment_delivery` | |
| S2d | Semantic | Open a model that was never published and click **Discard draft** | The dialog is titled "Discard the draft and everything in it?" and states how many data models, metrics and dimensions will be lost; the model stays in the list but empty | |
| S3 | Semantic | Delete a model that is not published | One confirmation, then the row disappears and a green notice appears | |
| S4 | Semantic | Delete a published model | The dialog says Ask Data will stop using it; **Delete and remove from Ask Data** stays disabled until you type the model key; afterwards the model is gone, it is no longer the default, and Ask Data no longer answers from it | |
| A1 | Ask Data | How many orders per month? | Jan 1014, Feb 904, Mar 1002, Apr 963, May 969, Jun 1074, Jul 1035, Aug 1039. Tabs Summary, Table, Query filled | |
| A2 | Ask Data | Which region has the highest late delivery rate? | **Kalimantan Timur, 23.1%** (Jawa Timur is next at 16.3%) | |
| A3 | Ask Data | Late delivery rate by carrier | NusaCargo 13.2%, KilatKirim 11.3%, FastExpress 9.8% | |
| A4 | Ask Data | Late delivery rate in Jawa Timur (a value in the question) | **16.3%**, with a note that it is filtered to Jawa Timur | |
| A5 | Ask Data | Late delivery rate by region and carrier | Table of region x carrier; Kalimantan Timur x NusaCargo **32.2%** is the highest | |
| A6 | Drill-across | Late delivery rate and average fulfillment time by region | One table, two metric columns. Late rate as in A2; hours: Bali 15.8, DKI Jakarta 15.5, Jawa Barat 15.5, Jawa Tengah 15.1, Jawa Timur 15.4, Kalimantan Timur 15.7, Sulawesi Selatan 15.5, Sumatera Utara 15.3. The answer says each metric was computed separately | |
| A7 | Published view | Late rate by product category | Home & Living **16.3%**, Grocery 11.3, Electronics 10.1, Fashion 10.1, Beauty 9.2 (answered from the view) | |
| A8 | Published view | Late rate by channel | Marketplace 12.4%, Mobile App 10.9, Website 10.9 | |
| A9 | Ask Data | Average fulfillment time by channel | Marketplace 20.1 h, Website 14.1, Mobile App 13.9 | |
| A10 | Ask Data | What is the cancellation rate? | **3.8%** | |
| A11 | No join | Return rate by product category | Not answered with a number: no published model has both the return rate and the category. It must say so or ask, never invent a join | |
| G1 | Map | Late delivery rate by region, then open the **Map** tab (it appears only when a result has provinces) | The map of Indonesia with the 8 provinces coloured pale to deep orange; Kalimantan Timur (23.1%) is the deepest, then Jawa Timur (16.3%). The list on the right is ordered the same way | |
| G2 | Map | On the Map tab, switch **Areas** to **Bubbles** | Circles at each province; Kalimantan Timur has the largest | |
| G3 | Map | Hover a province; drag the map; use the zoom buttons and Reset | A tooltip with the province and value; the map pans and zooms; Reset returns to the full view | |
| G4 | Map | Ask something with no province (late rate by carrier) | No **Map** tab | |
| G5 | Map | Ask late rate by region and carrier, then open the Map tab (if present) | Provinces repeat across carriers; the map sums them per province or the tab is absent. Record which | |
| A12 | Out of scope | What is our net profit? | Says it is not in the published metrics | |
| A13 | Comparison | Compare the late delivery rate of Sumatera Utara from March to May with June to August 2026 | Two periods in one row: earlier **6.0%**, later **15.6%**, change **+9.6 points**. The answer names both periods and says the rate rose | |
| A14 | Comparison | Compare the late delivery rate by region from March to May with June to August 2026 | One row per province with earlier, later and change. Sumatera Utara +9.6, Kalimantan Timur -3.4 (23.8 to 20.4), DKI Jakarta -2.0 (9.7 to 7.7) | |
| A15 | Benchmark | Which regions are above the overall late delivery rate? | **Jawa Timur (16.3%) and Kalimantan Timur (23.1%)**, with the overall rate **11.3%** and the difference for each. The answer says the overall rate is computed over all shipments, not the average of the regions | |
| A16 | Benchmark | Which regions are more than 4 points above the overall late delivery rate? | Both Jawa Timur (+5.0) and Kalimantan Timur (+11.8) pass; the same question with 8 points keeps only Kalimantan Timur | |
| A17 | Benchmark | Which regions are below the overall late delivery rate? | The other six provinces (all under 11.3%), listed lowest first | |
| A18 | Comparison | Compare the late delivery rate of Sumatera Utara between March-May and June-August (no year) | Same as A13: the most recent finished year is used, **6.0%** then **15.6%** | |
| A19 | Benchmark | How does Kalimantan Timur late delivery rate compare to the overall rate? | One row: **23.15%**, overall **11.3%**, difference about **+11.85 points** | |
| A20 | Benchmark | Compare the late delivery rate by region with the overall rate | All 8 regions, each with overall 11.3% and its difference, Kalimantan Timur first | |
| A21 | Explain | Any Ask Data answer, click **How this was calculated** | One-line summary, then metric, formula, breakdown, period, filters, source. Same wording whatever the model | |
| A22 | Verify | `How many orders do we get per month?` | Check line says the result is split by month; months in date order | |
| A23 | Understand | `Bisa bantu compare late delivery di stumatra udtara antara maret dan juni` | Region read as **Sumatera Utara** with the note “stumatra udtara” was read as …; two periods **2026-03** and **2026-06** compared (one query each, see **How this was calculated**); no “no date filter” warning | |
| A24 | Understand | `Late delivery rate di sumatera` | Not filtered; a note asks whether Sumatera Utara or Sumatera Barat was meant | |
| A25 | Understand | `Bandingkan late delivery Sumatera Utara bulan Maret dengan bulan Juni` | Two periods compared, same as A23 | |
| AG1 | Agent | Why is Kalimantan Timur late so often? | Progress shows steps; answer cites step numbers; NusaCargo **32.2%** stands out; **How this was calculated** lists 3 to 5 steps | |
| AG2 | Agent | What should we do about carrier performance in Kalimantan Timur? (library with both PDFs exists) | Includes a document step; recommendation applies the **15%** review and **25%** hold thresholds and names the PDF and page | |
| AG3 | Agent | Set `AGENT_MODE_ENABLED=false`, ask AG1 again | Normal single-query answer, no steps | |
| J1 | Judge | In a Session: `python scripts/judge_answers.py --cases samples/fulfillment/judge_conversation.json --out judge.json` | The 11-question Indonesian POV conversation is asked in one session and every answer is checked against the sample data (route, metric, top row, numbers in the text, language, no repeated labels). `11 of 11 answers pass`; send `judge.json` back for any FAIL | |
| Q1 | Answer quality | Semantic Layer > Answer quality > Paste several, paste `samples/fulfillment/benchmark_examples.txt`, Save | 8 examples listed | |
| Q2 | Answer quality | Run benchmark | 8 of 8 pass; a run appears under Recent runs with the published version | |
| Q3 | Answer quality | Add the instruction `Always show late delivery rate with 1 decimal`, Save, ask a late rate question | The answer follows the instruction | |
| K1 | Knowledge | Create a library, upload `Delivery_Returns_Policy.pdf` and `Carrier_Operations_Guide.pdf`, wait for **Ready** | Ready, 5 pages indexed per file | |
| K2 | Knowledge | (attach the library) What is the service level of regular delivery? | **4 days** (Express 2 days), cited to page 1 | |
| K3 | Knowledge | When is a carrier review triggered? | Late rate above **15%** in a region in a month; above 25% new volume is held. Cited to page 2 | |
| K4 | Knowledge | What compensation does a customer get for a very late delivery? | More than 2 days after the service level: voucher of **10% of the order value, up to IDR 50,000**. Page 3 | |
| K5 | Knowledge | Can I return an opened beauty product? | **No** (hygiene). Return window 7 days, electronics defects 14 days. Page 4 | |
| K6 | Knowledge | What is the pick and pack target for marketplace orders? | **36 hours** (24 hours for other orders). Page 5 | |
| K7 | Knowledge | What is the courier insurance policy? | Says it cannot answer from the library; no invented policy | |
| K8 | Knowledge | Click a `Page N` chip or the source file | The PDF opens at that page | |
| K9 | Knowledge | Run `python scripts/eval_retrieval.py --questions samples/fulfillment/retrieval_eval.json --label reranker-off` in a Session | A list of six questions with the rank of the right page and a summary (hit@1, hit@3, hit@5, MRR, mean ms). With the 5-page policy, hit@5 should be 1.0 | |
| K10 | Knowledge | Add the project variable `ENABLE_RERANKER=true`, run the Install and Deploy Jobs, repeat K9 with `--label reranker-on` | The card shows the bge reranker; the summary is the same or better; record the mean ms | |
| M1 | MCP | Register the server (stdio, backend venv Python, `samples/fulfillment/late_delivery_server.py`), **Test connection** | Success; tool `assess_delivery_risk` listed | |
| M2 | MCP | (attach the server) Assess a Regular Home & Living shipment to Kalimantan Timur with NusaCargo in July | Probability **0.35**, band High, policy: volume hold above 25% | |
| M3 | MCP | Assess a Regular Fashion shipment in DKI Jakarta with FastExpress | Probability **0.07**, band Low, no action | |
| M4 | MCP | Assess a shipment to "Mars" | A message listing the valid regions; no crash | |
| R1 | Routing | A data question with the library chip attached | Answered from the library (the chip decides), or says it is not there | |
| R2 | Routing | A policy question with no chip | Answered by Ask Data (no chip is Ask Data), not from the documents | |
| X1 | Known limit | Which region and carrier pairs are above the policy review threshold? | Data side: Kalimantan Timur x NusaCargo 32.2, Jawa Timur x FastExpress 17.8, Sumatera Utara x KilatKirim 16.4, Jawa Timur x NusaCargo 15.9, Jawa Timur x KilatKirim 15.1. The 15% threshold lives in the policy: record whether the two sources are combined | |
| PR1 | Prompts | Open Prompts, Create prompt | Internal keys offered: `ask_data.system`, `rag.system`, `rag.insufficient_evidence`; no scope choice | |
| PR2 | Prompts | Create and **Publish** `ask_data.system`: "Answer in at most two sentences and end with: Governed answer." Re-ask A2 | The answer follows the new instruction | |
| PR3 | Prompts | Create version 2, publish it, then **Rollback** to version 1 | A2 answers in the style of the published version each time | |
| PR4 | Prompts | Publish `rag.insufficient_evidence`: "Not in the policy library." Re-ask K7 | The custom sentence is used | |
| PR5 | Prompts | Save a draft without publishing, then re-ask A2 | The draft has no effect until published | |
| F1 | Features | Settings -> **Features** | Ask Data, Semantic Layer, Data Sources, Usage and Settings show **Always on** with a reason and no switch; only Knowledge, Prompts and Skills have a switch (Skills is off by default) | |
| F2 | Features | Switch **Prompts** off | The Prompts menu disappears at once, without a reload; opening `/prompts` shows "Prompts is turned off" with a link back to Settings; the row says "Changed from default (On)" | |
| F3 | Features | Reload the page and open it in another browser | The change is still there (it is stored for the workspace, not in the browser) | |
| F4 | Features | Switch **Knowledge** off | The Knowledge menu and the library choice in the chat are gone; the libraries are still there when it is switched on again | |
| F5 | Features | **Reset to deployment defaults** | Every switch returns to its starting point | |
| SK1 | Skills | Settings -> Features: switch **Skills** on | The **Skills** menu appears at once (it is off by default; no redeploy needed) | |
| SK2 | Skills | New skill, handler `prompt_only`, a prompt such as "You are a delivery analyst", **Publish**, run it with a question | A text answer that follows the prompt | |
| SK3 | Skills | New skill, handler `ask_data`, tool `ask_data`, run it with "Late delivery rate by carrier" | Same numbers as A3 | |
| SK4 | Skills | New skill, handler `rag`, tool `rag_search`, run it with the K3 question | A grounded answer with the page citation | |
| SK5 | Skills | Save a skill with handler `ask_data` but without the `ask_data` tool | Rejected with a clear message | |

## Record

| Item | Value |
|---|---|
| Date and tester | |
| Workspace, Application sizes | |
| Passed / Failed / Partial (not counting *known limit* rows) | |
| Notes (what was surprising) | |
