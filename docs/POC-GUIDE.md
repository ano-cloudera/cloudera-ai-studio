# Bring the accelerator to a new PoC

Anywhere AI Studio is a platform, not a single use case. A PoC supplies its own data, definitions, documents and tools;
the platform stays the same. This guide lists what to change and where. Use it after the AMP is imported
(see the README, "Deploy as an AMP").

## 1. What stays, what changes

| Stays (do not edit per PoC) | Changes per PoC |
|---|---|
| Backend, Frontend, Qdrant, deploy Jobs | LLM provider and model |
| Governed Ask Data pipeline, RAG pipeline, MCP client | Data Source (Trino, Impala or PostgreSQL) and its credentials |
| Settings, usage and prompt management UI | Semantic model: entities, dimensions, metrics, business definitions, synonyms |
| | Knowledge libraries and documents |
| | MCP servers (tools the assistant may call) |
| | Starter questions, branding, extra prompts |

## 2. Checklist (about one hour with data in hand)

1. **Import the AMP** with the LLM key and the data source variables. Add any other secret the PoC needs as a project
   variable and list its name in `AMP_FORWARD_ENV` (comma separated). Run the `deploy-applications` Job again after adding variables.
2. **LLM.** Settings -> AI Models: add a provider with a key reference `env://YOUR_KEY_NAME`, add a model, assign it to the capabilities
   (Ask Data, Knowledge, MCP). No GPU is needed for hosted models. To serve your own model, see "Optional: vLLM" in the README.
3. **Data Source.** Data Sources -> new connection (Trino, Impala or PostgreSQL). Passwords are entered as `env://VARIABLE`, never as text.
   Test the connection, then browse the tables.
4. **Semantic layer.** Semantic Layer -> create a model, add each table as an entity, import columns as dimensions, define metrics with a
   plain-language description and synonyms, then **Publish**. Only published metrics answer questions. Pin the model in Settings -> Ask Data
   so questions resolve to it without typing `@`. Write each metric as a formula over columns (for example a ratio of two counts).
5. **Knowledge.** Knowledge -> create a library per topic and upload the documents (PDF, text). Wait for **Ready**. Attach a library with `@`
   to answer from it; answers cite the document and page.
6. **MCP tools.** Settings -> MCP -> add a server (stdio command or HTTP URL), pass secrets by variable name, **Test connection**, **Save**.
   Attach it with `@` to call its tools.
7. **Starter questions and look.** Settings -> Ask Data for the starter questions. Branding is set with the `NEXT_PUBLIC_*` variables in
   `deployment/cai/manifests/applications.yaml` (the Frontend is rebuilt by the deploy Job).
8. **Try it.** Ask the same three kinds of question in separate chats: a data question (no chip), a document question (library chip)
   and a tool question (MCP chip).

## 3. How questions are routed

The chip decides the source. No chip means Ask Data on the pinned semantic model. A library chip means answers from those documents only.
An MCP chip means the assistant plans a call to that server's tool, runs it and explains the result. Start a **New chat** when you switch
source so earlier context does not carry over. The composer shows a tip when a question looks like it belongs to a chip.

## 4. Sizing and limits

- Application sizes are in `deployment/cai/manifests/applications.yaml`; override per PoC with `AMP_<APP>_CPU`, `AMP_<APP>_MEMORY_GB`
  (for example `AMP_BACKEND_MEMORY_GB=16` for large PDFs) and run the deploy Job again.
- The Backend runs as one replica with SQLite on the project filesystem. Do not open the database file from a Session while it runs.
- Qdrant on NFS is not officially supported by Qdrant. Keep the source documents; re-ingest if the index is damaged.
- A new secret is read when the Backend starts, so restart it (re-run the deploy Job) after adding one.

## 5. Optional sample pack

`demo/data` holds two synthetic credit-risk tables and `scripts/mcp/` an approval-likelihood MCP server. Sample policy documents are not shipped.
Load it with `scripts/cai/load_credit_risk_demo.py` to rehearse the flow, then replace it with the PoC's own content.

## 6. Troubleshooting

| Symptom | Check |
|---|---|
| Question goes to the wrong source | Which chip is attached; start a New chat |
| "Cannot answer from documents" | The question is outside the attached library |
| Data question cannot be answered | The metric is not published, or the dimension is not on the entity |
| Backend cannot reach Qdrant | Application authentication settings, then `QDRANT_URL` on the Backend |
| Secret not found | The variable exists in the project, is listed in `AMP_FORWARD_ENV`, and the deploy Job ran again |
