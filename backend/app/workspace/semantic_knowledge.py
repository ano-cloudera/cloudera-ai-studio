"""What a team tells Ask Data about one semantic model, kept with the workspace settings.

* instructions: business rules, terms and defaults ("fiscal year starts in April", "late means after the service level").
  They reach the analyst with every answer from that model.
* examples: questions with an optional known answer. They double as the benchmark: run them against the published
  model and see which still answer correctly.
* runs: the last benchmark runs, so a new version can be compared with the one before it.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

SEMANTIC_KNOWLEDGE_KEY = "semantic_knowledge"
MAX_INSTRUCTIONS = 4000
MAX_EXAMPLES = 50
MAX_RUNS = 10


class ExampleQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=500)
    expected_value: float | None = Field(default=None, description="The number the first matching row must show; empty = not checked.")
    tolerance: float = Field(default=0.05, ge=0, description="Allowed difference from the expected value, in the metric's own units.")
    match: str | None = Field(default=None, max_length=120, description="Look at the row that contains this text (for example a region); empty = the first row.")

    @field_validator("question")
    @classmethod
    def tidy(cls, value: str) -> str:
        return " ".join(value.split())


class BenchmarkRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at: str
    published_version: int | None = None
    passed: int
    total: int


class SemanticKnowledge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instructions: str = Field(default="", max_length=MAX_INSTRUCTIONS)
    examples: list[ExampleQuestion] = Field(default_factory=list, max_length=MAX_EXAMPLES)
    runs: list[BenchmarkRun] = Field(default_factory=list, max_length=MAX_RUNS)


def read_semantic_knowledge(settings_json: dict | None, model_id: str) -> SemanticKnowledge:
    block = (settings_json or {}).get(SEMANTIC_KNOWLEDGE_KEY)
    entry = block.get(str(model_id)) if isinstance(block, dict) else None
    if not isinstance(entry, dict):
        return SemanticKnowledge()
    try:
        return SemanticKnowledge.model_validate(entry)
    except ValueError:
        return SemanticKnowledge()  # stored by an older shape: start clean rather than fail the page


def write_semantic_knowledge(settings_json: dict | None, model_id: str, value: SemanticKnowledge) -> dict[str, Any]:
    merged = dict(settings_json or {})
    block = dict(merged.get(SEMANTIC_KNOWLEDGE_KEY) or {})
    block[str(model_id)] = value.model_dump()
    merged[SEMANTIC_KNOWLEDGE_KEY] = block
    return merged
