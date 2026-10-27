# Chat context model (post-UAT M9)

## ChatContextSource

Unified composer context:

| type | id | routing |
|------|-----|---------|
| `knowledge_library` | library UUID | Knowledge RAG (library scope) |
| `uploaded_file` | attachment UUID | Temporary document RAG (document scope) |

Mixed `knowledge_library` + `uploaded_file` in one request returns `mixed_context_unsupported` (422).

## Entry paths

- Knowledge detail → **Ask this library** → `sessionStorage` pending context
- Chat `@` mention picker
- Chat **+ → Knowledge** (same picker semantics)

Gate: `CHAT_CONTEXT_UNIFICATION_PASS` (Vitest).

## Request shape

```json
{
  "message": "...",
  "context_sources": [
    { "type": "uploaded_file", "id": "<attachment-uuid>", "name": "report.pdf" }
  ]
}
```

Server resolves attachment → backing document IDs; filenames are display-only.
