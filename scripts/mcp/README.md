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
| Arguments | `/home/cdsw/cloudera-ai-studio/scripts/mcp/credit_risk_server.py` |
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
