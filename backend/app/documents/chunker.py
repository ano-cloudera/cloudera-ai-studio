from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.documents.parsed import ParsedDocument


@dataclass(frozen=True)
class TextChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    workspace_id: uuid.UUID
    project_id: uuid.UUID
    library_id: uuid.UUID
    chunk_index: int
    text: str
    page_number: int | None
    section: str | None
    token_count: int
    metadata: dict


class TokenChunker:
    """Deterministic character-window chunker (≈4 chars per token)."""

    def __init__(self, *, chunk_size_tokens: int, chunk_overlap_tokens: int) -> None:
        self.chunk_size = max(64, chunk_size_tokens) * 4
        self.chunk_overlap = max(0, min(chunk_overlap_tokens, chunk_size_tokens // 2)) * 4

    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)

    def chunk(
        self,
        parsed: ParsedDocument,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        library_id: uuid.UUID,
    ) -> list[TextChunk]:
        source = parsed.text.strip()
        if not source and parsed.pages:
            source = "\n\n".join(p.text for p in parsed.pages if p.text.strip())
        if not source:
            return []

        chunks: list[TextChunk] = []
        start = 0
        index = 0
        while start < len(source):
            end = min(len(source), start + self.chunk_size)
            piece = source[start:end].strip()
            if piece:
                page_number = None
                section = None
                if parsed.pages:
                    page_number = parsed.pages[min(index, len(parsed.pages) - 1)].page_number
                if parsed.sections:
                    section = parsed.sections[min(index, len(parsed.sections) - 1)].title
                chunks.append(
                    TextChunk(
                        chunk_id=uuid.uuid4(),
                        document_id=parsed.document_id,
                        workspace_id=workspace_id,
                        project_id=project_id,
                        library_id=library_id,
                        chunk_index=index,
                        text=piece,
                        page_number=page_number,
                        section=section,
                        token_count=self._estimate_tokens(piece),
                        metadata={"title": parsed.title},
                    )
                )
                index += 1
            if end >= len(source):
                break
            start = max(end - self.chunk_overlap, start + 1)
        return chunks
