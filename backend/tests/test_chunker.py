from __future__ import annotations

import uuid

from app.documents.chunker import TokenChunker
from app.documents.parsed import ParsedDocument


def test_chunker_deterministic():
    doc_id = uuid.uuid4()
    ws, proj, lib = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    parsed = ParsedDocument(document_id=doc_id, title="t", text="word " * 2000)
    chunker = TokenChunker(chunk_size_tokens=100, chunk_overlap_tokens=10)
    a = chunker.chunk(parsed, workspace_id=ws, project_id=proj, library_id=lib)
    b = chunker.chunk(parsed, workspace_id=ws, project_id=proj, library_id=lib)
    assert len(a) == len(b) > 1
    assert a[0].chunk_index == 0
    assert a[0].workspace_id == ws
    assert a[0].document_id == doc_id
