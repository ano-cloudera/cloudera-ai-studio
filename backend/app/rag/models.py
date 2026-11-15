from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.models import StrictModel
from app.core.sections import SectionTable

GroundingLevel = Literal["SUPPORTED", "PARTIALLY_SUPPORTED", "INSUFFICIENT_EVIDENCE"]


class RagActionItem(BaseModel):
    """Something the document obliges someone to do: who, what, by when. A part the document does not give is left empty."""

    model_config = ConfigDict(extra="ignore")

    owner: str = ""
    action: str = ""
    deadline: str = ""


class RagLlmOutput(StrictModel):
    grounding: GroundingLevel
    direct_answer: str
    executive_summary: str
    insights: list[str] = []
    business_implications: list[str] = []
    caveats: list[str] = []
    cited_chunk_ids: list[str] = []
    # The layout is made by code from these, not asked of the model as markdown (see app/core/sections.py).
    key_points: list[str] = Field(default_factory=list)  # the provisions, as short points
    steps: list[str] = Field(default_factory=list)  # what the document says to do, in its order, one step each, with the page
    levels: SectionTable | None = None  # several levels, roles or thresholds side by side
    action_items: list[RagActionItem] = Field(default_factory=list)
    # Up to two things the reader may ask next that the passages supplied already answer; each is checked against the library
    # before it is shown (see RAGService.grounded_follow_ups), so a suggestion is never a question the documents cannot answer.
    follow_up_questions: list[str] = Field(default_factory=list)
