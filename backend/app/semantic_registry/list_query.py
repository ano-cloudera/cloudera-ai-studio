"""In-memory search/sort/pagination for semantic registry lists (Phase 2 UX)."""
from __future__ import annotations

from typing import Any, Callable, Sequence


def _sort_key(row: Any, field: str) -> str:
    if field == "updated_at" or field == "modified":
        val = getattr(row, "updated_at", None) or getattr(row, "created_at", None)
        return str(val or "")
    if field == "created_at":
        return str(getattr(row, "created_at", "") or "")
    val = getattr(row, field, None)
    if val is None and field == "name":
        val = getattr(row, "term", None)
    return str(val or "").casefold()


def apply_list_query(
    rows: Sequence[Any],
    *,
    search: str | None,
    sort: str | None,
    order: str | None,
    page: int | None,
    page_size: int | None,
    allowed_sort: frozenset[str],
    search_text: Callable[[Any], str],
) -> tuple[list[Any], int]:
    items = list(rows)
    needle = (search or "").strip().casefold()
    if needle:
        items = [r for r in items if needle in search_text(r).casefold()]

    sort_field = (sort or "modified").strip().casefold()
    if sort_field not in allowed_sort:
        sort_field = "modified" if "modified" in allowed_sort else ("name" if "name" in allowed_sort else next(iter(allowed_sort)))
    reverse = (order or "desc").strip().casefold() == "desc"
    items.sort(key=lambda r: _sort_key(r, sort_field), reverse=reverse)

    total = len(items)
    if page is not None and page_size is not None:
        p = max(page, 1)
        ps = max(min(page_size, 200), 1)
        start = (p - 1) * ps
        items = items[start : start + ps]
    return items, total
