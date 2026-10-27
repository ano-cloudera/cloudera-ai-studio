from __future__ import annotations

from app.retrieval.citations import candidate_to_citation
from app.retrieval.types import RetrievalCandidate, RetrievedContext


class ContextBuilder:
    def __init__(self, *, max_context_tokens: int) -> None:
        self._max_tokens = max(1, int(max_context_tokens))

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return max(1, len(text) // 4)

    def build(self, query: str, ranked: list[RetrievalCandidate], *, total_candidates: int) -> RetrievedContext:
        selected: list[RetrievalCandidate] = []
        used = 0
        for candidate in ranked:
            need = self._estimate_tokens(candidate.text)
            if selected and used + need > self._max_tokens:
                break
            if not selected and need > self._max_tokens:
                # include at least one truncated evidence block
                truncated = candidate
                selected.append(truncated)
                used = self._max_tokens
                break
            selected.append(candidate)
            used += need

        citations = [candidate_to_citation(c) for c in selected]
        return RetrievedContext(
            query=query,
            evidence=selected,
            citations=citations,
            total_candidates=total_candidates,
            selected_candidates=len(selected),
            token_budget_used=used,
        )
