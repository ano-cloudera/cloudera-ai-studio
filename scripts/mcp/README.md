# Credit Risk MCP demo

An MCP server that exposes an approval-likelihood model for credit applications. The model is trained on the
synthetic `demo/data/credit_applications.csv`; it is an **advisory indicator** (it never approves or rejects).

| File | Purpose |
|---|---|
| `train_credit_model.py` | Trains the model (needs scikit-learn) and writes `credit_risk_model.json` |
| `credit_risk_model.json` | Coefficients, thresholds and hold-out metrics (committed) |
| `credit_risk_scoring.py` | Scores an application in plain Python (no ML runtime) |
| `credit_risk_server.py` | MCP server (stdio), tool `assess_application_risk` |

## Register it (Settings → MCP connections)

| Field | Value on Cloudera AI |
|---|---|
| Name | `Credit Risk Model` |
| Description | `Advisory approval-likelihood model for credit applications (synthetic data).` |
| Transport | `stdio` |
| Command | `/home/cdsw/.venvs/studio-backend/bin/python` (the backend's Python, where `mcp` is installed) |
| Arguments | `/home/cdsw/anywhere-ai-studio/scripts/mcp/credit_risk_server.py` |
| Default tool | leave empty (the model reads the tool schema and fills the arguments) |

Use **Test connection**; it should list `assess_application_risk`. Then pick the connector with `@` in Ask Data:

> Assess an applicant with credit score 640, DTI 0.40, requested 150 million, Digital, Jawa Barat.

If a required value (credit score or DTI) is missing from the question, the assistant asks for it instead of guessing.

## Retrain

```bash
python scripts/mcp/train_credit_model.py   # rewrites credit_risk_model.json
```

To serve the model from a Cloudera AI Model endpoint instead, replace the body of `assess()` in
`credit_risk_scoring.py` with an HTTP call to the endpoint; the MCP tool and the planner stay unchanged.

# Operations Desk MCP (agent actions)

An MCP server where follow-up tickets are raised and listed (`ops_desk_server.py`). The agent proposes a ticket from what the
data showed; the user approves it in the chat (button **Run**), and only then is `create_ticket` called. `create_ticket` is
annotated as an action (`readOnlyHint: false`); only such tools are ever proposed. `list_tickets` is read-only.

Tickets are kept in `OPS_DESK_FILE` (default `~/anywhere-studio-data/ops_desk/tickets.json`, the project storage). To send them
to ServiceNow, Jira, SAP PM or email instead, replace `_save()`; the tools and the agent stay the same.

## Register it (Settings → MCP connections)

| Field | Value on Cloudera AI |
|---|---|
| Name | `Operations Desk` |
| Description | `Raise and list follow-up tickets for operational issues.` |
| Transport | `stdio` |
| Command | `/home/cdsw/.venvs/studio-backend/bin/python` |
| Arguments | `/home/cdsw/anywhere-ai-studio/scripts/mcp/ops_desk_server.py` |

**Test connection** should list `create_ticket` and `list_tickets`. Then ask the agent what to do, for example:

> Apa yang sebaiknya kita lakukan untuk Papua Maluku?

The answer ends with **Proposed actions**; each shows its arguments and runs only when you click **Run**. Proposals need the
tool loop (`AGENT_LOOP=tools`).
