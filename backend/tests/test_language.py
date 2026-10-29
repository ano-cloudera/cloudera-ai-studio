from __future__ import annotations

import pytest

from app.core.language import detect_language


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("How many credit applications do we have in total?", "en"),
        ("What is our delinquency rate in Q3 2026?", "en"),
        ("Compare the approval rate by region and channel from June to August 2026.", "en"),
        ("Berapa total aplikasi kredit kita?", "id"),
        ("Bandingkan approval rate per wilayah dan channel selama Juni sampai Agustus 2026.", "id"),
        ("total approval rate", "en"),
        ("selamat pagi", "id"),
        ("halo", "id"),
        ("hallo kamu bisa bantu apa bisa apa ?", "id"),
        ("terima kasih", "id"),
        ("hello", "en"),
        ("hi, what can you help with?", "en"),
        ("good morning", "en"),
        ("", "en"),
        (None, "en"),
    ],
)
def test_detect_language_defaults_to_english(text, expected):
    assert detect_language(text) == expected
