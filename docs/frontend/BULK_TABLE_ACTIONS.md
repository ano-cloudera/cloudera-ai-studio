# Bulk table actions (reusable pattern)

## Selection model

- Immutable **IDs** in a `Set<string>` (`useTableSelection`).
- Header checkbox: **current page only** (checked / unchecked / indeterminate).
- Selection **persists across pagination** within the current view.
- **Clear selection** always available when count &gt; 0.

## Bulk action bar

- Shown when `selectedCount > 0`.
- Actions: **Clear selection**, **Delete selected** (never “Delete all”).
- Partial failures: success toast + normalized error lines; **failed IDs stay selected**.

## Backend

| Endpoint | Body |
|----------|------|
| `POST /api/v1/libraries/bulk-delete` | `{ "ids": ["…"] }` |
| `POST /api/v1/documents/bulk-delete` | `{ "library_id": "…", "ids": ["…"] }` |

Response: `requested`, `deleted[]`, `failed[]`, `deleted_count`, `failed_count`.

- Reuses single-item delete services (same guards and cleanup).
- Best-effort per item (not atomic).
- Duplicate IDs deduplicated on input.
- Max items: `BULK_DELETE_MAX_ITEMS` (default **100**); code `BULK_DELETE_LIMIT_EXCEEDED`.

## Implemented surfaces

- Knowledge **libraries** landing table
- Knowledge **documents** table (library detail)

## Future candidates (not implemented)

Prompts, Skills, Connectors, Semantic Layer — same hooks/components where applicable.
