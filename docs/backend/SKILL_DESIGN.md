# Skills — Design (M3B)

## Concept

A **skill** is reusable, versioned task configuration:

- Instructions (skill-specific layer)
- Optional **prompt reference** (`prompt_key` → M3A `PromptResolver`)
- **Allowed tools** (registry-controlled capability names)
- Input/output JSON schemas (optional validation)
- **Handler type** in `config`: `prompt_only`, `ask_data`, `rag`

## Scope

| scope | workspace_id | project_id |
|-------|--------------|------------|
| workspace | required | null |
| project | required | required |

Resolution: **project → workspace** (no global marketplace in M3B).

## Tool registry

`app/skills/tool_registry.py` — validates tool keys and handler requirements.

Tools map to **existing** accelerator capabilities; they are not separate microservices.

## Execution contract

`SkillExecutionContext` carries resolved skill version, project/workspace ids, user input, resolved prompt (if any), and allowed tools.

Execution is **explicit** via `/skills/{id}/execute` only — no hybrid router or agent loop in M3B.

## Security

- Tool list is closed; unknown tools rejected at version create/publish
- Project skills cannot execute outside their project/workspace
- No code execution, shell, or connector tools in M3B

## Out of scope (M3B)

Semantic layer manager, connectors, automatic skill routing, ReAct, dynamic LangGraph builder, RBAC.
