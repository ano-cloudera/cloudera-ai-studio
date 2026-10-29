from __future__ import annotations

from app.documents.file_response import document_file_response_meta


def test_pdf_opens_inline_with_a_pdf_media_type() -> None:
    media_type, headers = document_file_response_meta("Credit approval policy.pdf", "application/pdf")
    assert media_type == "application/pdf"
    assert headers["Content-Disposition"].startswith("inline;")
    assert "Credit%20approval%20policy.pdf" in headers["Content-Disposition"]
    assert headers["X-Content-Type-Options"] == "nosniff"


def test_pdf_is_recognised_by_extension_when_the_mime_type_is_generic() -> None:
    media_type, headers = document_file_response_meta("policy.PDF", "application/octet-stream")
    assert media_type == "application/pdf"
    assert headers["Content-Disposition"].startswith("inline;")


def test_other_files_download_and_are_never_rendered_by_the_browser() -> None:
    media_type, headers = document_file_response_meta("notes.html", "text/html")
    assert media_type == "application/octet-stream"
    assert headers["Content-Disposition"].startswith("attachment;")
    assert headers["X-Content-Type-Options"] == "nosniff"


def test_filename_cannot_break_out_of_the_header() -> None:
    _, headers = document_file_response_meta('a"\r\nSet-Cookie: x=1.pdf', "application/pdf")
    value = headers["Content-Disposition"]
    assert "\r" not in value and "\n" not in value
    assert value.count('"') == 2
