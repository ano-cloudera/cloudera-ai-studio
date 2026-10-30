"""Workspace-level Ask Data starter question settings."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.ask_data.presentation_tier_config import PresentationTierOverrides

ASK_DATA_SETTINGS_KEY = "ask_data"
MAX_STARTER_QUESTIONS = 6
MAX_QUESTION_LENGTH = 500
DEFAULT_CAPTION = "Start with a question"

StarterSource = Literal["configured", "question_bank", "semantic_runtime"]


class AskDataSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    starter_questions_caption: str = Field(default=DEFAULT_CAPTION, max_length=120)
    starter_questions: list[str] = Field(default_factory=list, max_length=MAX_STARTER_QUESTIONS)
    starter_source: StarterSource = "configured"
    question_bank_limit: int = Field(default=3, ge=1, le=20)
    # Kept so settings saved by older versions still load; the question bank itself was removed.
    question_bank_domain: str | None = None
    question_bank_difficulty: str | None = None
    presentation: PresentationTierOverrides | None = None
    default_semantic_model_id: str | None = Field(
        default=None,
        description="Pinned published semantic model (UUID). Used when Ask Data has no @ context.",
    )
    auto_attach_semantic_model: bool = Field(
        default=True,
        description="When true, attach pinned model or the only published model in the project.",
    )
    instruction_prompt_key: str | None = Field(
        default=None,
        max_length=120,
        description="Optional workspace prompt key injected as Genie-style space instructions for governed Ask Data.",
    )

    @field_validator("starter_questions")
    @classmethod
    def normalize_questions(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in value:
            text = " ".join(str(raw).split()).strip()
            if not text or text in seen:
                continue
            cleaned.append(text[:MAX_QUESTION_LENGTH])
            seen.add(text)
            if len(cleaned) >= MAX_STARTER_QUESTIONS:
                break
        return cleaned

    @field_validator("starter_questions_caption")
    @classmethod
    def normalize_caption(cls, value: str) -> str:
        text = " ".join(str(value).split()).strip()
        return text or DEFAULT_CAPTION


def read_ask_data_settings(settings_json: dict | None) -> AskDataSettings:
    block = (settings_json or {}).get(ASK_DATA_SETTINGS_KEY) or {}
    if not isinstance(block, dict):
        block = {}
    return AskDataSettings.model_validate(block)


def write_ask_data_settings(settings_json: dict | None, settings: AskDataSettings) -> dict:
    merged = dict(settings_json or {})
    merged[ASK_DATA_SETTINGS_KEY] = settings.model_dump()
    return merged


def resolve_starters(settings: AskDataSettings) -> dict:
    caption = settings.starter_questions_caption

    questions = [
        {
            "id": f"configured-{index}",
            "question": text,
            "domain": "",
            "domains": [],
            "difficulty": "simple",
            "analysis_type": "starter",
            "expected_visualization": "table",
        }
        for index, text in enumerate(settings.starter_questions)
    ]
    return {
        "caption": caption,
        "source": "configured",
        "questions": questions,
    }


def resolve_starters_with_runtime(
    settings: AskDataSettings,
    semantic_context: Any | None,
    *,
    deployment_settings: Any | None = None,
) -> dict:
    """Same precedence as capability insights: configured → golden → published metrics."""
    base = resolve_starters(settings)
    if base.get("questions"):
        return base
    if semantic_context is None:
        return base
    from app.ask_data.capability_catalog import resolve_example_questions

    texts = resolve_example_questions(
        semantic_context,
        configured_starters=None,
        limit=MAX_STARTER_QUESTIONS,
        settings=deployment_settings,
    )
    if not texts:
        return base
    return {
        "caption": settings.starter_questions_caption,
        "source": "semantic_runtime",
        "questions": [
            {
                "id": f"runtime-{index}",
                "question": text,
                "domain": "",
                "domains": [],
                "difficulty": "simple",
                "analysis_type": "starter",
                "expected_visualization": "table",
            }
            for index, text in enumerate(texts)
        ],
    }
