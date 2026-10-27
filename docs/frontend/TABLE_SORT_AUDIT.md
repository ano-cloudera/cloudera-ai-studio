# Table sort audit (Cloudera AI Studio)

Standard contract: `sort=<field>&order=asc|desc`, default **Modified DESC** (`updated_at` / `modified_at`).

| Surface | Paginated | Sortable columns (implemented / planned) | Default | Notes |
|---------|-----------|------------------------------------------|---------|-------|
| **Knowledge — libraries** | Yes | name, document_count, created_at, updated_at | updated_at DESC | **V2.1** |
| **Knowledge — documents** | Yes | original_filename, mime_type, size_bytes, chunk_count, status, created_at, updated_at | updated_at DESC | **V2.1** |
| Semantic Layer | Partial | Registry tables vary; many client-side | — | Migrate in future milestone |
| Prompts | Partial | name, updated_at where API supports | updated_at DESC | Audit only this milestone |
| Skills | Partial | name, updated_at | updated_at DESC | Audit only |
| Connectors | Partial | name, updated_at | updated_at DESC | Audit only |
| Usage | Events list | timestamp only | DESC | Not column-sort UI |
| AI Models / assignments | Registry | name, provider | — | See AI Registry UI |
| Settings | Minimal | N/A | — | No sortable tables |

Invalid `sort` values fall back to **updated_at** server-side (whitelist); never raw SQL interpolation.
