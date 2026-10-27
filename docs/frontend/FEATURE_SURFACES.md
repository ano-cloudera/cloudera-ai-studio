# Feature surfaces

| Route | Sidebar | Flag | Purpose |
|-------|---------|------|---------|
| `/` | Ask Data | `NEXT_PUBLIC_FEATURE_ASK_DATA` | Governed / RAG chat |
| `/knowledge` | Knowledge | `NEXT_PUBLIC_FEATURE_DOCUMENTS` | Libraries, documents, retrieval test |
| `/prompts` | Prompts | `NEXT_PUBLIC_FEATURE_PROMPTS` | Prompt CRUD, versions, publish |
| `/skills` | Skills | `NEXT_PUBLIC_FEATURE_SKILLS` | Skill config, tools, test execute |
| `/semantic-layer` | Semantic Layer | `NEXT_PUBLIC_FEATURE_SEMANTIC_LAYER` | Model lifecycle and definitions |
| `/connectors` | Connectors | `NEXT_PUBLIC_FEATURE_CONNECTORS` | Datasource registry |
| `/usage` | Usage | `NEXT_PUBLIC_FEATURE_USAGE` | Token usage |
| `/settings` | Settings | `NEXT_PUBLIC_FEATURE_SETTINGS` | Workspace settings |

API proxy (Next.js rewrites in `frontend/next.config.mjs`):

| Browser path | Backend path |
|--------------|--------------|
| `/api/v1/*` | `/api/v1/*` |
| `/api/models`, `/api/random-queries`, `/api/chat/*`, `/api/usage/*` | same path **without** extra `/api` prefix on backend |
| `/api/health`, `/api/health/ready`, `/api/version` | `/health`, `/health/ready`, `/version` |

After changing rewrites, **restart** the Next dev server. Smoke: `frontend/scripts/proxy-route-gate.sh`.
