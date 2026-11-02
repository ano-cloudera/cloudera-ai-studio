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

1. **Import the AMP** and click Launch without editing the form (an edited value can be saved as `[object Object]`). Then, in
   Project Settings -> Advanced, add the LLM key and the data source variables (button **+**, then **Submit**), and any other secret the
   PoC needs as a variable with its name listed in `AMP_FORWARD_ENV` (comma separated). Run the `deploy-applications` Job again after
   adding variables. Details and the repair command are in the README.
2. **LLM.** Settings -> AI Models: add a provider with a key reference `env://YOUR_KEY_NAME`, add a model, assign it to the capabilities
   (Ask Data, Knowledge, MCP). No GPU is needed for hosted models. To serve your own model, see "Optional: vLLM" at the end of this guide.
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

## Sizing the Applications

Each Application's CPU and memory are set in `deployment/cai/manifests/applications.yaml` (Qdrant 4 vCPU / 8 GB,
Backend 4 vCPU / 8 GB, Frontend 2 vCPU / 4 GB, vLLM 16 vCPU / 64 GB / 1 GPU) and applied by the deploy Job. To size one PoC differently
without editing the file, add project variables `AMP_<APP>_CPU`, `AMP_<APP>_MEMORY_GB` or `AMP_<APP>_GPU` (for example `AMP_BACKEND_MEMORY_GB=16`; raise the Backend memory if you load large PDFs, which Docling parses in memory)
and run the deploy Job again. The workspace still limits the maximum per Application.

## Optional: vLLM (your own model on a GPU)

Off by default. Most PoCs do not need it: register an external model endpoint or an API key
in Settings -> AI Models instead. To serve your own model, add `ENABLE_VLLM=true` and `VLLM_MODEL_ID` in Project Settings (and set `GPU_PROFILE`, plus
`HUGGING_FACE_HUB_TOKEN` for gated models). The setup job then also builds the vLLM virtualenv and downloads the weights, and the deploy job
creates a fourth Application, `anywhere-vllm`, with one GPU. This needs, outside the AMP:
- GPU nodes and quota in the workspace, and a **GPU-enabled runtime**: put its identifier in `AMP_VLLM_RUNTIME_ID`
  (the standard runtime cannot use the GPU). Ask the workspace admin if no GPU runtime is listed.
- Enough disk on the project filesystem for the weights, and a GPU large enough for the model (adjust `GPU_PROFILE`, `MAX_MODEL_LEN`,
  `GPU_MEMORY_UTILIZATION`; see `deployment/cai/env/studio-vllm.env.example`).
When the Application runs, the deploy job prints the base URL to register in Settings -> AI Models (OpenAI-compatible provider, `<url>/v1`).
If the vLLM install or start fails, the other three Applications are unaffected; fix it and run the `deploy-applications` Job again.
