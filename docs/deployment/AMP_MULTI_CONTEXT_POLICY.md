# AMP — multi-context policy (Ask Data)

**Audience:** SE, implementers, customer architects  
**Scope:** Cloudera AI Studio accelerator (any vertical). Golden Banking is a **reference bundle**, not a product boundary.

## Layers (what “global” means today)

| Layer | What it is | Typical POC |
|-------|------------|-------------|
| **Deployment** | One backend + DB + Qdrant + `.env` | Local 8001 / CAI staging |
| **Workspace** | Ask Data settings: pin, auto-attach, starters, presentation | Single `default` workspace → Settings feel app-wide |
| **Project** | Published semantic models, chat execution scope | Default project only |
| **Chat session** | Multi-turn governed memory, guardrails | New chat = new session |
| **Per message** | Composer `@` chips (`context_sources`) | One **family** per send |

There is **no** per-project Ask Data settings UI yet. Pin applies at **workspace** level; the pinned model must exist in the **current project**.

## Three context families (never mix in one request)

| Family | Composer | Server mode | Use for |
|--------|----------|-------------|---------|
| **Structured / governed** | `@` semantic model, metric, entity, term, table | `ask_data` | KPIs, breakdowns, governed SQL |
| **Knowledge** | `@` knowledge library | `rag` | Policies, SOPs, indexed PDFs |
| **Uploaded file** | `@` attachment (chat upload) | `rag` | Ad-hoc document Q&A |
| **MCP** | `@` MCP connector | `mcp` | External / builtin tools (env `MCP_CONNECTORS_JSON`) |

Mixing families returns a validation error. See [CHAT_CONTEXT_MODEL.md](../frontend/CHAT_CONTEXT_MODEL.md) and [SEMANTIC_LAYER_V2.md](../frontend/SEMANTIC_LAYER_V2.md).

## Default behavior without `@`

When `context_sources` is empty:

1. **Guardrails** and structured precedence run first.
2. If `auto_attach_semantic_model` is **true** (workspace settings):
   - Use **`default_semantic_model_id`** (pin) when set and published in this project, **or**
   - Auto-attach when **exactly one** published model exists in the project.
3. If **two or more** published models and **no pin** → **no** automatic semantic attach. User must **`@` a model/metric** or set pin in Settings.

Removing all `@` chips on the next message returns to step 2 (not “sticky RAG”).

## Multi-semantic (multiple ontologies)

| Strategy | When to use |
|----------|-------------|
| **Pin one hero model** (recommended for AMP demo) | Stable “no `@`” story for primary domain |
| **`@` semantic / metric** | Secondary domain in same workspace/project |
| **Separate deployment or preset** | Customer wants isolated default domain (e.g. credit-only env) |

Product gap (post-AMP): clarification chip to pick among published models when unpinned — same UX pattern as metric chips (UAT-6).

There is **no** automatic “documents vs metrics” chooser; scope is explicit via chips or pin.

## MCP (Settings)

Configure MCP servers in **Settings → MCP connections** (workspace `settings_json.mcp`):

- **stdio** — `command` + `args` (e.g. `npx -y @modelcontextprotocol/server-brave-search`)
- **SSE** — remote `url`
- Secrets: list **env var names** only (`BRAVE_API_KEY` on Backend CAI Application); values are never stored in Settings.

Enabled servers appear in Ask Data **`@` → MCP**. One server per message.

API: `GET/PUT /api/v1/mcp/settings`, `GET /api/v1/mcp/connectors`.

## Accelerator apply script

`apply_accelerator_demo_profile.py` merges presentation preset and, by default, **pins the hero semantic** from preset `hero_semantic_model_key`(s) or the sole published model. Use `--skip-pin` to leave pin unchanged.

Preset: [accelerator-demo-presentation.json](../../config/examples/accelerator-demo-presentation.json).

## Related

- [AMP_ACCELERATOR_PLAYBOOK.md](./AMP_ACCELERATOR_PLAYBOOK.md)
- [AMP_VERTICAL_SWAP_CHECKLIST.md](./AMP_VERTICAL_SWAP_CHECKLIST.md)
- Spec Kit reference instance: [AMP_BANKING](../testing/spec-kit/AMP_BANKING/00-spec.md)
