# Knowledge UX V2 (post-UAT)

Engineering baseline: **M8_KNOWLEDGE_UX_V2** — not covered by M7E UAT sign-off.

## Surfaces

- **Knowledge landing**: compact table (search, sort, pagination), create-library modal, row actions (open, rename, ask, delete).
- **Library detail**: header with capacity `count / limit`, centered empty upload state, document table (search, status filter, pagination), overflow actions.

## Chat context

- Shared type: `ChatContextSource` (`knowledge_library` only in this milestone).
- **Ask this library** stores pending context in session storage and navigates to main chat.
- **@ picker** in the main composer attaches the same structured context (ID + name).
- Chat requests send optional `context_sources`; backend normalizes to `mode=rag` + scoped `library_ids`.
- No attached knowledge → existing Ask Data behavior unchanged.
- Attached knowledge → explicit library-scoped RAG (no hybrid Ask Data routing).

## Document limit

- Config: `KNOWLEDGE_MAX_DOCUMENTS_PER_LIBRARY` (default **100**).
- Backend code: `LIBRARY_DOCUMENT_LIMIT_REACHED` (HTTP 409).
- Frontend disables upload at capacity and shows warning from 80%.

## Bulk actions (FE-KNOWLEDGE-01.2)

- Checkbox column + page select-all + ID-based selection across pages.
- Bulk delete via `POST …/bulk-delete` (see [BULK_TABLE_ACTIONS.md](./BULK_TABLE_ACTIONS.md)).

## Polish (FE-KNOWLEDGE-01.1)

- Landing row menu: **Edit** (not Open/Rename), **Ask this library**, **Delete**; row click still opens detail.
- **Edit library** modal via portal (`document.body`), z-index ≥ 100, body scroll lock, overlay dismiss.
- Library detail document table: stable `min-h-[450px]` flex column; pagination pinned to bottom.

## Known limitations

- Context picker category is Knowledge-only; architecture allows future source types.
- Multi-library context is supported when multiple chips are attached; backend accepts multiple library IDs for RAG scope.
- Library delete cascades document + vector cleanup (behavior change from empty-library-only delete).

## API

Paginated list shape when `page` / `page_size` (or search/sort) query params are present:

```json
{ "items": [], "page": 1, "page_size": 10, "total": 0, "total_pages": 0 }
```

Legacy `{ "libraries": [] }` / `{ "documents": [] }` responses remain when pagination params are omitted.
