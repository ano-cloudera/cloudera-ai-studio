"""A suggestion under a document answer is kept only when the library can answer it, and never more than two."""
from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.rag.models import RagLlmOutput
from app.services.rag_service import RAGService


def _service(min_score: float = 0.5) -> RAGService:
    return RAGService(SimpleNamespace(rag_min_rerank_score=min_score))  # type: ignore[arg-type]


def _row(score: float) -> dict:
    ident = str(uuid.uuid4())
    return {"chunk_id": ident, "document_id": ident, "library_id": ident, "workspace_id": ident, "project_id": ident, "text": "t", "rerank_score": score}


class _Retrieval:
    """Finds evidence only for the questions it was told about."""

    def __init__(self, scores: dict[str, float]) -> None:
        self.scores = scores
        self.asked: list[str] = []

    def retrieve(self, *, query: str, **_: object) -> dict:
        self.asked.append(query)
        score = self.scores.get(query)
        return {"results": [_row(score)] if score is not None else []}


def _ask(service: RAGService, retrieval: _Retrieval, questions: list[str], asked: str = "Apa itu Level 1?") -> list[str]:
    return service.grounded_follow_ups(retrieval, questions, asked=asked, workspace_id=uuid.uuid4(), project_id=uuid.uuid4(), scoped=[uuid.uuid4()], scoped_docs=False)  # type: ignore[arg-type]


def test_only_a_suggestion_the_library_answers_is_kept() -> None:
    retrieval = _Retrieval({"Apa itu Level 2?": 0.9, "Siapa CEO perusahaan?": 0.1})
    assert _ask(_service(), retrieval, ["Siapa CEO perusahaan?", "Apa itu Level 2?"]) == ["Apa itu Level 2?"]


def test_never_more_than_two_and_never_the_question_just_asked() -> None:
    questions = ["Apa itu Level 1?", "A?", "B?", "C?"]
    retrieval = _Retrieval({"A?": 0.9, "B?": 0.9, "C?": 0.9})
    assert _ask(_service(), retrieval, questions) == ["A?", "B?"]
    assert "Apa itu Level 1?" not in retrieval.asked


def test_a_failing_check_drops_the_suggestion_without_failing_the_answer() -> None:
    class Broken:
        def retrieve(self, **_: object) -> dict:
            raise RuntimeError("down")

    assert _ask(_service(), Broken(), ["A?"]) == []  # type: ignore[arg-type]


def test_the_model_output_accepts_suggestions_and_defaults_to_none() -> None:
    base = {"grounding": "SUPPORTED", "direct_answer": "a", "executive_summary": "b"}
    assert RagLlmOutput.model_validate(base).follow_up_questions == []
    assert RagLlmOutput.model_validate({**base, "follow_up_questions": ["x?"]}).follow_up_questions == ["x?"]
