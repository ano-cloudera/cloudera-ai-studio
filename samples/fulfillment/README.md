# Fulfillment and delivery sample (non-banking)

A second, synthetic use case for the accelerator: an online retailer's **orders** (fulfillment) and **shipments** (delivery).
Use it to try the three sources on a domain other than credit risk: governed Ask Data over two tables, Knowledge over a delivery
policy, and an MCP tool that estimates late-delivery risk. All data is synthetic and generated with a fixed seed.

| File | What it is |
|---|---|
| `data/orders.csv` (8,000 rows), `data/shipments.csv` (about 7,700 rows) | The two tables. They share `order_id` and `region_name` |
| `generate_data.py` | Regenerates the CSVs (identical every time) |
| `expected_answers.py` | Prints the correct answer for the test questions, computed from the CSVs |
| `load_fulfillment_demo.py` | Loads both tables into Trino and creates the joined view `v_fulfillment_delivery` |
| `make_policy_pdf.py` | Writes the 5-page sample policy PDF (kept out of git) |
| `late_delivery_server.py` | MCP server (stdio) with the advisory tool `assess_delivery_risk` |
| `SEMANTIC-MODEL.md` | The entities, dimensions and metrics to create in the Semantic Layer |

## Set it up

In a Session terminal of the project (backend venv):

```bash
export PATH=/home/cdsw/tools/node/bin:$PATH
PY=/home/cdsw/.venvs/studio-backend/bin/python
cd /home/cdsw
TRINO_CATALOG=hive TRINO_SCHEMA=default $PY samples/fulfillment/load_fulfillment_demo.py      # needs TRINO_HOST/USER/PASSWORD
$PY samples/fulfillment/make_policy_pdf.py                                                    # writes samples/fulfillment/knowledge/
```

Then in the Frontend: add the Trino **Data Source**, build the model from [SEMANTIC-MODEL.md](SEMANTIC-MODEL.md) and **Publish** it,
create a Knowledge library and upload `Delivery_Returns_Policy.pdf`, and register the MCP server
(command: the backend venv Python, argument: `samples/fulfillment/late_delivery_server.py`). The test table is in
[docs/TEST-PLAN.md](../../docs/TEST-PLAN.md).

## How "joins" work here

Runtime joins are disabled on purpose: the model never writes a join. There are three ways to combine the two tables:

1. **Drill-across**: ask for two metrics, each from its own table, that share a dimension (late delivery rate and average fulfillment time
   by region). Each metric is computed from its own governed formula and the results are merged by the shared dimension.
   Both tables must be entities of **one** model.
2. **Published view**: the data owner creates `v_fulfillment_delivery` in Trino (order columns joined to shipment columns) and publishes it
   as an entity. Questions that need columns from both tables (late rate by product category) are answered from the view.
3. **No join available**: a question that needs a join nobody published is answered with "not supported", not guessed.

## Maps

The 8 regions are real Indonesian provinces (DKI Jakarta, Jawa Barat, Jawa Tengah, Jawa Timur, Sumatera Utara, Kalimantan Timur,
Sulawesi Selatan, Bali). Any Ask Data result that has a province column and a numeric column gets a **Map** tab: provinces coloured by
the value (Areas) or sized circles (Bubbles). The boundaries are bundled in the Frontend (`public/geo/indonesia-provinces.json`,
Natural Earth, public domain), so the map works offline and sends no data anywhere.
