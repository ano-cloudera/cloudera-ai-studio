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
| P5 | Platform | Data Sources -> add Trino (password `env://TRINO_PASSWORD`), **Test connection**, browse the tables | Connection OK; `fulfillment_orders`, `delivery_shipments`, `v_fulfillment_delivery` visible | |
| P6 | Platform | Run the **Deploy applications** Job again with no change | Finishes, all Applications Running (about 3 min, plus about 30 s per Application update) | |
| S1 | Semantic | Create one model with the 3 entities from [SEMANTIC-MODEL.md](../samples/fulfillment/SEMANTIC-MODEL.md), **Publish** | Published; the metrics appear under "Browse published metrics" | |
| A1 | Ask Data | How many orders per month? | Jan 1014, Feb 904, Mar 1002, Apr 963, May 969, Jun 1074, Jul 1035, Aug 1039. Tabs Summary, Table, Query filled | |
| A2 | Ask Data | Which region has the highest late delivery rate? | **Kalimantan, 23.1%** (Jawa Timur is next at 16.3%) | |
| A3 | Ask Data | Late delivery rate by carrier | NusaCargo 13.2%, KilatKirim 11.3%, FastExpress 9.8% | |
| A4 | Ask Data | Late delivery rate in Jawa Timur (a value in the question) | **16.3%**, with a note that it is filtered to Jawa Timur | |
| A5 | Ask Data | Late delivery rate by region and carrier | Table of region x carrier; Kalimantan x NusaCargo **32.2%** is the highest | |
| A6 | Drill-across | Late delivery rate and average fulfillment time by region | One table, two metric columns. Late rate as in A2; hours: Bali-Nusa Tenggara 15.8, Jabodetabek 15.5, Jawa Barat 15.5, Jawa Tengah 15.1, Jawa Timur 15.4, Kalimantan 15.7, Sulawesi 15.5, Sumatera 15.3. The answer says each metric was computed separately | |
| A7 | Published view | Late rate by product category | Home & Living **16.3%**, Grocery 11.3, Electronics 10.1, Fashion 10.1, Beauty 9.2 (answered from the view) | |
| A8 | Published view | Late rate by channel | Marketplace 12.4%, Mobile App 10.9, Website 10.9 | |
| A9 | Ask Data | Average fulfillment time by channel | Marketplace 20.1 h, Website 14.1, Mobile App 13.9 | |
| A10 | Ask Data | What is the cancellation rate? | **3.8%** | |
| A11 | No join | Return rate by product category | Not answered with a number: no published model has both the return rate and the category. It must say so or ask, never invent a join | |
| A12 | Out of scope | What is our net profit? | Says it is not in the published metrics | |
| A13 | Known limit | Compare the late rate of Sumatera from March-May with June-August | Truth: 6.0% vs 15.6% (+9.6 points). Record what happens (two-period comparison is not implemented) | |
| A14 | Known limit | Which regions are above the overall late rate? | Truth: Jawa Timur and Kalimantan (overall 11.3%). Record what happens (benchmark comparison is not implemented) | |
| K1 | Knowledge | Create a library, upload `Delivery_Returns_Policy.pdf`, wait for **Ready** | Ready, 5 pages indexed | |
| K2 | Knowledge | (attach the library) What is the service level of regular delivery? | **4 days** (Express 2 days), cited to page 1 | |
| K3 | Knowledge | When is a carrier review triggered? | Late rate above **15%** in a region in a month; above 25% new volume is held. Cited to page 2 | |
| K4 | Knowledge | What compensation does a customer get for a very late delivery? | More than 2 days after the service level: voucher of **10% of the order value, up to IDR 50,000**. Page 3 | |
| K5 | Knowledge | Can I return an opened beauty product? | **No** (hygiene). Return window 7 days, electronics defects 14 days. Page 4 | |
| K6 | Knowledge | What is the pick and pack target for marketplace orders? | **36 hours** (24 hours for other orders). Page 5 | |
| K7 | Knowledge | What is the courier insurance policy? | Says it cannot answer from the library; no invented policy | |
| K8 | Knowledge | Click a `Page N` chip or the source file | The PDF opens at that page | |
| M1 | MCP | Register the server (stdio, backend venv Python, `samples/fulfillment/late_delivery_server.py`), **Test connection** | Success; tool `assess_delivery_risk` listed | |
| M2 | MCP | (attach the server) Assess a Regular Home & Living shipment to Kalimantan with NusaCargo in July | Probability **0.35**, band High, policy: volume hold above 25% | |
| M3 | MCP | Assess a Regular Fashion shipment in Jabodetabek with FastExpress | Probability **0.07**, band Low, no action | |
| M4 | MCP | Assess a shipment to "Mars" | A message listing the valid regions; no crash | |
| R1 | Routing | A data question with the library chip attached | Answered from the library (the chip decides), or says it is not there | |
| R2 | Routing | A policy question with no chip | Answered by Ask Data (no chip is Ask Data), not from the documents | |
| X1 | Known limit | Which region and carrier pairs are above the policy review threshold? | Data side: Kalimantan x NusaCargo 32.2, Jawa Timur x FastExpress 17.8, Sumatera x KilatKirim 16.4, Jawa Timur x NusaCargo 15.9, Jawa Timur x KilatKirim 15.1. The 15% threshold lives in the policy: record whether the two sources are combined | |
| PR1 | Prompts | Open Prompts, Create prompt | Internal keys offered: `ask_data.system`, `rag.system`, `rag.insufficient_evidence`; no scope choice | |
| PR2 | Prompts | Create and **Publish** `ask_data.system`: "Answer in at most two sentences and end with: Governed answer." Re-ask A2 | The answer follows the new instruction | |
| PR3 | Prompts | Create version 2, publish it, then **Rollback** to version 1 | A2 answers in the style of the published version each time | |
| PR4 | Prompts | Publish `rag.insufficient_evidence`: "Not in the policy library." Re-ask K7 | The custom sentence is used | |
| PR5 | Prompts | Save a draft without publishing, then re-ask A2 | The draft has no effect until published | |
| SK1 | Skills | Add the project variable `NEXT_PUBLIC_FEATURE_SKILLS` = `true`, run the Deploy Job, reload | The **Skills** menu appears (it is off by default) | |
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
