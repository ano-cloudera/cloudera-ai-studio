# Operations Desk (a sample MCP server with an action)

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
| Arguments | `/home/cdsw/anywhere-ai-studio/samples/ops_desk/ops_desk_server.py` |

**Test connection** should list `create_ticket` and `list_tickets`. Then ask the agent what to do, for example:

> Apa yang sebaiknya kita lakukan untuk Papua Maluku?

The answer ends with **Proposed actions**; each shows its arguments and runs only when you click **Run**. Proposals need the
tool loop (`AGENT_LOOP=tools`).

## Where approved actions are recorded

Every action a person approves with **Run** is recorded by the platform itself (server, tool, arguments, time, result or error),
whichever MCP server it was sent to, and listed in **Actions** (menu, Monitor). That page appears once an enabled MCP server has an
action tool or an action has been run. This sample is only one server that provides an action; any MCP server whose tool says it
changes something (`readOnlyHint: false`) is offered the same way.
