from __future__ import annotations

import pytest

from app.documents.validation import UploadValidationError, validate_upload


def test_accepts_pdf():
    data = b"%PDF-1.4\n"
    result = validate_upload(filename="report.pdf", data=data, max_bytes=1024, allowed_types={"pdf"})
    assert result.mime_type == "application/pdf"


def test_rejects_oversized():
    with pytest.raises(UploadValidationError) as exc:
        validate_upload(filename="a.txt", data=b"x" * 20, max_bytes=10, allowed_types={"txt"})
    assert exc.value.code == "file_too_large"


def test_rejects_disallowed_extension():
    with pytest.raises(UploadValidationError) as exc:
        validate_upload(filename="evil.exe", data=b"MZ", max_bytes=1024, allowed_types={"pdf", "txt"})
    assert exc.value.code == "unsupported_type"
