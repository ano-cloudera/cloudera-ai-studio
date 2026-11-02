# Demo guide

## Configure the demo (step by step)

Open the Frontend Application. Everything below is done in the UI except step 2.

## 1. Choose the LLM

**Settings → AI Models** → add a provider (for example Gemini) and pick the key variable (for example `GEMINI_API_KEY`) from the **Secret reference** list,
add a model, and assign it to the capabilities (Ask Data, Knowledge, MCP). The UI text and answers are English;
an answer follows the language of the question.

## 2. Load the demo data into Trino (Session terminal)

```bash
cd /home/cdsw/anywhere-ai-studio
/home/cdsw/.venvs/studio-backend/bin/python -m pip install trino   # if not already present
TRINO_HOST=<host> TRINO_USER=<user> TRINO_PASSWORD=<password> \
TRINO_CATALOG=hive TRINO_SCHEMA=default \
  /home/cdsw/.venvs/studio-backend/bin/python scripts/cai/load_credit_risk_demo.py --replace
```

This creates `credit_applications` (12,000 rows) and `loan_quality` (8,000 rows) as Parquet tables.
`scripts/cai/test_trino_connection.py` checks connectivity first.

## 3. Add the Data Source

**Data Sources → New connection** → Trino: host, port `443`, HTTPS, catalog `hive`, schema `default`,
user, and pick `TRINO_PASSWORD` from the **Secret reference** list (it shows the variables the Backend can read; values are never shown). Run **Test connection**, then browse the tables.

## 4. Build the semantic layer

**Semantic Layer** → create one model per table (`credit_applications`, `loan_quality`):

1. Add the table as an **entity** and import its columns as **dimensions**
   (for example `region_name`, `application_channel`, `customer_segment`, `application_date`).
2. Add **metrics** with business definitions and synonyms. The demo uses:

| Metric | Expression |
|---|---|
| Approval Rate (%) | `COUNT(CASE WHEN decision_status = 'Approved' THEN 1 END) * 100.0 / COUNT(application_id)` |
| Total Applications | `COUNT(application_id)` |
| Average Decision Time (hours) | `AVG(decision_time_hours)` |
| Policy-exception approvals | `COUNT(CASE WHEN decision_status = 'Approved' AND policy_exception_flag THEN 1 END)` |

3. **Publish** the model. Publishing validates the full artifact, and only published metrics are used to answer questions.
4. **Settings → Ask Data** → pin `credit_applications` as the default model, so questions resolve to it without an `@`.

## 5. Upload the knowledge documents

**Knowledge** → create a library (for example `Policy Knowledge`) and upload your documents (PDF or text). Wait until each document is
**Ready**. Documents are stored under `/home/cdsw/anywhere-studio-data/documents` and indexed in Qdrant; deleting a document in the UI also removes
its vectors and files.

## 6. Register the MCP server

**Settings → MCP** → **Add server**:

| Field | Value |
|---|---|
| Name | `Credit Risk Model` |
| Transport | `stdio` |
| Command | `/home/cdsw/.venvs/studio-backend/bin/python` |
| Arguments | `/home/cdsw/anywhere-ai-studio/scripts/mcp/credit_risk_server.py` |

Click **Test connection**; it should list `assess_application_risk`, then **Save**. See `scripts/mcp/README.md`.

---

## Run the demo

Start each part from **New chat** so no earlier context leaks in. The `@` chip decides the source:
no chip → Ask Data, `@<library>` → Knowledge, `@<MCP server>` → MCP.

**1. Ask Data** (no chip)

1. Which region has the lowest approval rate from June to August 2026?
2. Compare the approval rate by region and channel from June to August 2026.
3. What is the average decision time by channel?

**2. Knowledge** (attach your library, for example `@Policy Knowledge`)

1. When does an approval-rate gap trigger an investigation?
2. Can we say Branch is slower because of manual review?
3. What are the standard approval criteria?

Click a source file or a `Page N` chip to open the PDF at that page.

**3. MCP** (attach `@Credit Risk Model`)

> Assess an applicant with credit score 640, DTI 0.40, requested 150 million, Digital, Jawa Barat.

The result is an advisory approval likelihood (about 16%, Low band) with the policy checks.
It never approves or rejects an application.

Every Ask Data answer has **Summary**, **Table** and **Query** tabs; the Query tab shows the governed definition, the executed SQL and the source table.

## Update, restart and troubleshoot

| Change | What to do |
|---|---|
| Backend code | `git pull`, then **Restart** the Backend |
| Frontend code | `git pull`, `npm run build` in a Session, then **Restart** the Frontend and hard-refresh the browser |
| New secret | Add it to the Application, then **Restart** (the key is read at start) |

| Symptom | Likely cause |
|---|---|
| Frontend stays down, log says `Could not find a production build` | The last `npm run build` failed; rebuild and restart |
| `npm: command not found` | `export PATH=/home/cdsw/tools/node/bin:$PATH` |
| Backend `core_ready` but no answers | No model assigned in Settings → AI Models |
| Question answered by the wrong source | Wrong chip: no chip is Ask Data, a library chip is Knowledge |
| MCP test connection fails | Check the Arguments path ends in `credit_risk_server.py` and the Command is the backend venv Python |
| Knowledge answer says it cannot answer | The question is not covered by the attached library |
