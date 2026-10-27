from __future__ import annotations

import re

_EM_DASH = "\u2014"


def without_em_dash(text: str) -> str:
    """Replace em dashes in user-facing copy with plain punctuation."""
    if not text or _EM_DASH not in text:
        return text
    cleaned = text.replace(f" {_EM_DASH} ", ", ")
    cleaned = cleaned.replace(f"{_EM_DASH} ", ", ")
    cleaned = cleaned.replace(f" {_EM_DASH}", ",")
    cleaned = cleaned.replace(_EM_DASH, ", ")
    cleaned = re.sub(r",\s*,", ",", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()
