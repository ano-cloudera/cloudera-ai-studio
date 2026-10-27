from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int
    total_pages: int


def clamp_page(page: int) -> int:
    return max(1, page)


def clamp_page_size(page_size: int, *, maximum: int = 100) -> int:
    return max(1, min(page_size, maximum))


def total_pages(total: int, page_size: int) -> int:
    if total <= 0:
        return 0
    return (total + page_size - 1) // page_size
