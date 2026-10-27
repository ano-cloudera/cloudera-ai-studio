# Frontend UX audit (M6.1 product hardening)

## Resolved

- **Raw 404 in management UI (v1)**: First rewrite sent `/api/v1/*` correctly after adding `/api` segment; v1 management pages load.
- **Runtime proxy mismatch (M6.1 stabilization)**: A single rule `/api/:path*` → `backend/api/:path*` broke **legacy** routes (`/models`, `/chat/stream`, `/health/ready`) because they live on the backend **root**, not under `/api`. Fixed with explicit rewrite table in `next.config.mjs` + `scripts/proxy-route-gate.sh`.
- Pages use `ServiceErrorState` + `AppApiError` instead of HTTP status text.
- **Ask Data double-trigger**: Stream loop breaks on `done`; `turnInFlightRef` guards submit; progress cleared in `finally`. Regression test in `AskDataPage.test.tsx`.
- **Header “Database”**: Replaced with **Platform Ready** via `/api/health/ready`.
- **Hidden Prompts/Skills**: Feature flags default to enabled in `appConfig.ts`; routes `/prompts`, `/skills` in AppShell BUILD section.
- **Knowledge CRUD feel**: Library card landing, detail with Documents + Test tabs.
- **Semantic Layer action density**: Lifecycle strip + single primary CTA; secondary actions under Advanced.
- **Connector form**: Grouped General / Connection / Authentication / Security / Advanced.
- **Settings**: Tabs for General, AI models, RAG, Features, Advanced.

## Remaining limitations

- Semantic validation UX still exposes technical detail in places; further grouping optional.
- Connector browse UX unchanged beyond form hierarchy.
- Usage metrics limited to backend-exposed fields.
- Full mobile polish out of scope.

## Manual review checklist

- Ask Data landing + chat width with/without analysis panel
- Knowledge library create → upload → test retrieval
- Prompts/Skills publish and test tabs against live backend
- Connectors list + new connector + test connection
- Feature-flag profile with surfaces hidden
