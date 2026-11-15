"""Structured sections of an analysis, laid out by code.

A model that writes a long analysis as one markdown string tends to give one paragraph: no headings, no lists. So the layout is
not asked of the model as markdown. It fills sections (a kind, paragraphs, bullets, an optional table); this module turns them into
markdown with the headings of a fixed formal vocabulary in the language of the answer, so the structure and the register never
depend on how the model chose to format a string. The model decides what is said and which sections it needs; the code decides how
it is laid out.
"""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# kind -> (Indonesian, English). Only these; a kind the model invents falls back to the first.
TITLES: dict[str, tuple[str, str]] = {
    "detail": ("Penjelasan Detail", "Detailed Explanation"),
    "findings": ("Temuan Utama", "Key Findings"),
    "drivers": ("Faktor Pendorong", "Possible Drivers"),
    "implications": ("Implikasi Bisnis", "Business Implications"),
    "recommendations": ("Rekomendasi Tindakan", "Recommended Actions"),
    "verification": ("Langkah Verifikasi", "Verification Steps"),
    # documents
    "summary": ("Ringkasan", "Summary"),
    "provisions": ("Ketentuan Utama", "Key Provisions"),
    "steps": ("Langkah Penanganan", "Handling Steps"),
    "responsibilities": ("Penanggung Jawab", "Responsibilities"),
    "action_items": ("Tindak Lanjut", "Action Items"),
    "limits": ("Batasan Dokumen", "Document Limits"),
}
ANALYSIS_KINDS = ("detail", "findings", "drivers", "implications", "recommendations", "verification")
MAX_TABLE_ROWS = 6
MAX_TABLE_COLUMNS = 4


class SectionTable(BaseModel):
    model_config = ConfigDict(extra="ignore")

    header: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)

    @field_validator("header", mode="before")
    @classmethod
    def _header(cls, value: Any) -> Any:
        return [str(item) for item in value] if isinstance(value, list) else []

    @field_validator("rows", mode="before")
    @classmethod
    def _rows(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return []
        return [[str(cell) for cell in row] for row in value if isinstance(row, list)]


class AnalysisSection(BaseModel):
    """One part of an analysis. The heading is not the model's to write: it comes from `kind`."""

    model_config = ConfigDict(extra="ignore")

    kind: str = "detail"
    paragraphs: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)  # a numbered list, one step per item, in order
    bullets: list[str] = Field(default_factory=list)
    table: SectionTable | None = None

    @field_validator("paragraphs", "steps", "bullets", mode="before")
    @classmethod
    def _texts(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [value]
        return [str(item) for item in value if isinstance(item, (str, int, float))] if isinstance(value, list) else []


def title_for(kind: str, language: str) -> str:
    pair = TITLES.get((kind or "").strip().lower()) or TITLES["detail"]
    return pair[0] if language == "id" else pair[1]


def _clean(text: str) -> str:
    """One line of plain text, without the em dash the rest of an answer is also kept free of."""
    from app.services.text_sanitize import without_em_dash  # noqa: PLC0415

    return without_em_dash(" ".join(str(text).split()))


def table_to_markdown(table: SectionTable | None) -> str:
    """A pipe table of at most six rows and four columns, or nothing when the model gave no usable one."""
    if table is None or not table.header or not table.rows:
        return ""
    columns = min(MAX_TABLE_COLUMNS, len(table.header))
    header = [_clean(cell).replace("|", "/") for cell in table.header[:columns]]
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    for row in table.rows[:MAX_TABLE_ROWS]:
        cells = [_clean(cell).replace("|", "/") for cell in row[:columns]]
        cells += [""] * (columns - len(cells))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def sections_to_markdown(sections: list[AnalysisSection], language: str) -> str:
    """The sections as markdown: a `###` heading from the kind, the paragraphs, a bullet list, the table. An empty section is dropped."""
    blocks: list[str] = []
    for section in sections:
        parts: list[str] = []
        parts += [_clean(p) for p in section.paragraphs if _clean(p)]
        steps = [re.sub(r"^\s*\(?\d{1,2}[.)]\s*", "", _clean(s)) for s in section.steps if _clean(s)]
        if steps:
            parts.append("\n".join(f"{n}. {step}" for n, step in enumerate(steps, start=1)))
        bullets = [_clean(b) for b in section.bullets if _clean(b)]
        if bullets:
            parts.append("\n".join(f"- {b}" for b in bullets))
        table = table_to_markdown(section.table)
        if table:
            parts.append(table)
        if parts:
            blocks.append(f"### {title_for(section.kind, language)}\n\n" + "\n\n".join(parts))
    return "\n\n".join(blocks)
