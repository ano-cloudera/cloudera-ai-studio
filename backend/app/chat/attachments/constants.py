"""Reserved names and types for temporary chat attachments."""

from __future__ import annotations

CHAT_ATTACHMENTS_LIBRARY_NAME = "__cai_chat_attachments__"

CHAT_ATTACHMENT_ALLOWED_EXTENSIONS = frozenset({"pdf", "docx", "txt", "md", "markdown"})

ATTACHMENT_STATUS_UPLOADING = "UPLOADING"
ATTACHMENT_STATUS_QUEUED = "QUEUED"
ATTACHMENT_STATUS_PROCESSING = "PROCESSING"
ATTACHMENT_STATUS_READY = "READY"
ATTACHMENT_STATUS_FAILED = "FAILED"
ATTACHMENT_STATUS_EXPIRED = "EXPIRED"
