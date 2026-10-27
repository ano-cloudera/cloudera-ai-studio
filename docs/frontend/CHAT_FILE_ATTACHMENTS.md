# Chat file attachments (post-UAT M9)

## Supported types (V1)

PDF, DOCX, TXT, MD — max **5** files per batch, **25 MB** per file, **75 MB** per batch (env: `CHAT_ATTACHMENT_*`).

## Lifecycle

`UPLOADING` → `PROCESSING` → `READY` | `FAILED` | `EXPIRED`

Temporary attachments use hidden system library `__cai_chat_attachments__` (not listed in Knowledge UI). TTL default **7 days** (`CHAT_ATTACHMENT_TTL_DAYS`).

## API

- `POST /api/v1/chat/attachments/batch` (multipart: `session_id`, `files[]`)
- `GET /api/v1/chat/attachments/{id}`
- `POST /api/v1/chat/attachments/{id}/retry`
- `DELETE /api/v1/chat/attachments/{id}`
- `POST /api/v1/chat/attachments/{id}/save-to-knowledge`

## Knowledge bulk upload

`POST /api/v1/libraries/{id}/documents/batch-upload` — limits `KNOWLEDGE_UPLOAD_*`.

## Known limitations

- No images, CSV/XLSX, or scanned-PDF vision
- No hybrid Ask Data + RAG routing
- Mixed Knowledge + uploaded file blocked in V1
- Save to Knowledge API exists; dedicated composer UI action pending polish
