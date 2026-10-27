"""Upload validation for document intelligence (M2A)."""

from __future__ import annotations

from dataclasses import dataclass

# Magic-byte / structure sniffing (no extra deps).
_SIGNATURES: dict[str, list[tuple[bytes, str]]] = {
    "application/pdf": [(b"%PDF", "pdf")],
    "text/plain": [],  # validated by decode attempt
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [
        (b"PK\x03\x04", "docx"),
    ],
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [
        (b"PK\x03\x04", "xlsx"),
    ],
}

_EXTENSION_TO_MIME = {
    "pdf": "application/pdf",
    "txt": "text/plain",
    "md": "text/markdown",
    "markdown": "text/markdown",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


@dataclass(frozen=True)
class ValidatedUpload:
    mime_type: str
    extension: str
    size_bytes: int


class UploadValidationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def parse_allowed_types(raw: str) -> set[str]:
    parts = {p.strip().lower() for p in raw.split(",") if p.strip()}
    return parts or set(_EXTENSION_TO_MIME.keys())


def sniff_mime(data: bytes, filename: str) -> str | None:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in {"txt", "md", "markdown"}:
        try:
            data[:8192].decode("utf-8")
            return "text/plain" if ext == "txt" else "text/markdown"
        except UnicodeDecodeError:
            return None
    for mime, sigs in _SIGNATURES.items():
        if not sigs:
            continue
        for prefix, sig_ext in sigs:
            if data.startswith(prefix):
                if ext and ext != sig_ext and ext in ("docx", "xlsx") and sig_ext in ("docx", "xlsx"):
                    # ZIP-based Office formats share PK header; trust extension when allowed
                    return _EXTENSION_TO_MIME.get(ext)
                return mime
    return _EXTENSION_TO_MIME.get(ext)


def validate_upload(
    *,
    filename: str,
    data: bytes,
    max_bytes: int,
    allowed_types: set[str],
) -> ValidatedUpload:
    if not filename or not filename.strip():
        raise UploadValidationError("invalid_filename", "Filename is required")
    if len(data) > max_bytes:
        raise UploadValidationError("file_too_large", f"File exceeds maximum size ({max_bytes} bytes)")
    if len(data) == 0:
        raise UploadValidationError("empty_file", "File is empty")

    mime = sniff_mime(data, filename)
    if not mime:
        raise UploadValidationError("unsupported_type", "Unsupported or unrecognized file type")

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if not ext:
        for key, mapped in _EXTENSION_TO_MIME.items():
            if mapped == mime:
                ext = key
                break
    allowed_mimes = {_EXTENSION_TO_MIME.get(t, t) for t in allowed_types}
    if ext not in allowed_types and mime not in allowed_mimes:
        raise UploadValidationError("unsupported_type", "File type is not allowed")

    return ValidatedUpload(mime_type=mime, extension=ext or "bin", size_bytes=len(data))


def sanitize_storage_filename(original: str) -> str:
    """Safe basename for storage (no path segments)."""
    name = original.replace("\\", "/").split("/")[-1].strip()
    if not name or name in {".", ".."}:
        raise UploadValidationError("invalid_filename", "Invalid filename")
    safe = "".join(ch for ch in name if ch.isalnum() or ch in "._- ")
    safe = safe.strip().replace(" ", "_")[:200]
    if not safe:
        raise UploadValidationError("invalid_filename", "Invalid filename")
    return safe
