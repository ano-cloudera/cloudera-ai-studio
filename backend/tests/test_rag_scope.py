from __future__ import annotations

import uuid

from app.rag.citations_util import dedupe_citations
from app.rag.scope import bounded_rag_dialog, rag_scope_from_history
from app.retrieval.types import Citation


def test_rag_scope_from_history():
    lib = str(uuid.uuid4())
    history = [{"session_frame": {"mode": "rag", "rag_library_ids": [lib]}}]
    assert rag_scope_from_history(history) == [lib]


def test_bounded_rag_dialog_limits_turns():
    history = []
    for i in range(10):
        history.append(
            {
                "question": f"Q{i}",
                "answer": {"direct_answer": f"A{i}"},
            }
        )
    dialog = bounded_rag_dialog(history, max_turns=2)
    assert len(dialog) <= 4


def test_citation_dedupe():
    cid = uuid.uuid4()
    doc = uuid.uuid4()
    a = Citation(
        document_id=doc,
        filename="a.pdf",
        page_number=1,
        section=None,
        chunk_id=cid,
        source_uri=None,
        snippet="one",
        score=0.9,
    )
    b = Citation(
        document_id=doc,
        filename="a.pdf",
        page_number=1,
        section=None,
        chunk_id=cid,
        source_uri=None,
        snippet="one",
        score=0.8,
    )
    assert len(dedupe_citations([a, b])) == 1
