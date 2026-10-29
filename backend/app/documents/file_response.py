"""Headers for serving a stored document back to the browser (source preview)."""

from __future__ import annotations

import re
from urllib.parse import quote


def is_pdf(filename: str, mime_type: str) -> bool:
    return (mime_type or "").lower() == "application/pdf" or (filename or "").lower().endswith(".pdf")


def document_file_response_meta(filename: str, mime_type: str) -> tuple[str, dict[str, str]]:
    """Media type and headers: PDFs open inline, anything else downloads and is never sniffed or rendered."""
    name = (filename or "").strip() or "document"
    inline = is_pdf(name, mime_type)
    ascii_name = re.sub(r'[\r\n"\;]', "_", name.encode("ascii", "ignore").decode()).strip() or "document"
    disposition = "inline" if inline else "attachment"
    headers = {
        "Content-Disposition": f"{disposition}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name, safe='')}",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, max-age=300",
    }
    return ("application/pdf" if inline else "application/octet-stream"), headers
