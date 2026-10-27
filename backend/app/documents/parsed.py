from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class ParsedPage:
    page_number: int
    text: str
    metadata: dict = field(default_factory=dict)


@dataclass
class ParsedSection:
    title: str
    text: str
    page_number: int | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class ParsedDocument:
    document_id: uuid.UUID
    title: str
    text: str
    pages: list[ParsedPage] = field(default_factory=list)
    sections: list[ParsedSection] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
