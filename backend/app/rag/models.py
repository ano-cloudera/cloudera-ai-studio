from __future__ import annotations

from typing import Literal

from app.core.models import StrictModel

GroundingLevel = Literal["SUPPORTED", "PARTIALLY_SUPPORTED", "INSUFFICIENT_EVIDENCE"]


class RagLlmOutput(StrictModel):
    grounding: GroundingLevel
    direct_answer: str
    executive_summary: str
    insights: list[str] = []
    business_implications: list[str] = []
    caveats: list[str] = []
    cited_chunk_ids: list[str] = []
