from __future__ import annotations

from fastapi import APIRouter, Query

from app.semantic.questions import Difficulty, Domain, Question, QuestionBank


router = APIRouter()
bank = QuestionBank()


@router.get("/random-queries")
def random_queries(
    domain: Domain | None = None,
    difficulty: Difficulty | None = None,
    limit: int = Query(default=1, ge=1, le=20),
) -> dict[str, list[Question]]:
    return {"questions": bank.query(domain=domain, difficulty=difficulty, limit=limit)}
