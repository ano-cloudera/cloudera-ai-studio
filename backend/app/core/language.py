"""Answer-language detection: Studio text is English unless the user wrote in Indonesian."""

from __future__ import annotations

import re

_ID_MARKERS = frozenset(
    {
        "yang", "dan", "berapa", "apa", "apakah", "bagaimana", "tolong", "dengan", "untuk", "dari",
        "saya", "kita", "kami", "bandingkan", "tampilkan", "tunjukkan", "wilayah", "bulan", "tahun",
        "selama", "sampai", "adalah", "tidak", "ada", "pada", "itu", "ini", "atau", "mana", "semua",
        "seluruh", "jumlah", "kredit", "aplikasi", "persetujuan", "kenapa", "mengapa", "siapa",
        "kapan", "bisa", "boleh", "tertinggi", "terendah", "terbesar", "terkecil", "cabang", "toko",
        "selamat", "pagi", "siang", "sore", "malam", "halo", "hallo", "kamu", "anda", "bantu", "membantu",
        "terima", "kasih", "makasih", "tolong", "bintu",
    }
)
_EN_MARKERS = frozenset(
    {
        "the", "what", "how", "is", "are", "was", "were", "by", "of", "in", "for", "with", "and",
        "which", "who", "when", "why", "show", "compare", "list", "total", "many", "much", "our",
        "we", "you", "could", "would", "please", "me", "about", "from", "to", "top", "per",
    }
)

_WORD_RE = re.compile(r"[a-zA-Z']+")


def detect_language(text: str | None) -> str:
    """Return "id" when the text reads as Indonesian, otherwise "en" (the default)."""
    words = _WORD_RE.findall((text or "").casefold())
    id_hits = sum(1 for w in words if w in _ID_MARKERS)
    en_hits = sum(1 for w in words if w in _EN_MARKERS)
    return "id" if id_hits > en_hits else "en"
