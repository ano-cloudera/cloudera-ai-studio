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
        # Business questions that carry few of the words above ("Berapa pencapaian kuota per terminal?").
        "paling", "sering", "terlambat", "telat", "gimana", "gmn", "kondisi", "keseluruhan", "secara", "tingkat", "pencapaian",
        "terhadap", "dibanding", "dibandingkan", "sebelum", "sesudah", "setelah", "naik", "turun", "sebaiknya", "lakukan", "kuota",
        "pelanggan", "pengiriman", "penyaluran", "pendapatan", "penjualan", "produk", "rata", "dong", "nih", "aja", "banget",
        "lagi", "juga", "masih", "sudah", "belum", "akan", "harus", "perlu", "karena", "jika", "kalau", "supaya", "agar", "hari",
        "minggu", "kuartal", "triwulan", "jawaban", "lihat", "buat", "buatkan", "jelaskan", "ringkasan", "analisa", "analisis",
        "rekomendasi", "tindakan", "kenaikan", "penurunan", "terbanyak", "terbaik", "terburuk", "sering", "mulai", "dimana",
        "sebelumnya", "berikutnya", "lalu", "kemarin", "sekarang",
    }
)
_EN_MARKERS = frozenset(
    {
        "the", "what", "how", "is", "are", "was", "were", "by", "of", "in", "for", "with", "and",
        "which", "who", "when", "why", "show", "compare", "list", "many", "much", "our",
        "we", "you", "could", "would", "please", "me", "about", "from", "to",
    }
)
# A tie goes to Indonesian only when no word that is plainly English is present.
_STRONG_EN = frozenset({"the", "what", "how", "is", "are", "was", "were", "which", "who", "when", "why", "could", "would", "please", "about", "we", "you", "our"})

_WORD_RE = re.compile(r"[a-zA-Z']+")


def detect_language(text: str | None) -> str:
    """Return "id" when the text reads as Indonesian, otherwise "en" (the default)."""
    words = _WORD_RE.findall((text or "").casefold())
    id_hits = sum(1 for w in words if w in _ID_MARKERS)
    en_hits = sum(1 for w in words if w in _EN_MARKERS)
    if id_hits > en_hits:
        return "id"
    if id_hits and id_hits == en_hits and not any(w in _STRONG_EN for w in words):
        return "id"
    return "en"
