"""Semantic Layer V2 — context mix + publish issue mapping."""
from __future__ import annotations

import uuid

import pytest

from app.chat.context_sources import ContextSourceError, apply_context_sources, structured_data_sources
from app.core.models import AskDataRequest, ChatContextSource
from app.services.semantic_publish_orchestration import SemanticPublishOrchestrationService


def test_structured_data_sources_extracted():
    sources = [
        ChatContextSource(type="table", id="1", name="public.sales"),
        ChatContextSource(type="knowledge_library", id="2", name="Docs"),
    ]
    assert len(structured_data_sources(sources)) == 1
    assert structured_data_sources(sources)[0].type == "table"


def test_structured_context_passthrough_without_rag():
    req = AskDataRequest(
        session_id="s1",
        question="total sales",
        provider="gemini",
        model="gemini-3.8-flash",
        context_sources=[ChatContextSource(type="semantic_metric", id=str(uuid.uuid4()), name="Total Sales")],
    )
    class _Session:
        pass

    out = apply_context_sources(
        req,
        session=_Session(),
        project_id=uuid.uuid4(),
        conversation_history=[],
        settings=object(),
    )
    assert out.mode == "ask_data"
    assert out.context_sources[0].type == "semantic_metric"


def test_mixed_knowledge_and_structured_rejected():
    req = AskDataRequest(
        session_id="s1",
        question="q",
        provider="gemini",
        model="gemini-3.8-flash",
        context_sources=[
            ChatContextSource(type="knowledge_library", id=str(uuid.uuid4()), name="Docs"),
            ChatContextSource(type="table", id=str(uuid.uuid4()), name="sales"),
        ],
    )
    with pytest.raises(ContextSourceError) as exc:
        apply_context_sources(
            req,
            session=object(),
            project_id=uuid.uuid4(),
            conversation_history=[],
            settings=object(),
        )
    assert exc.value.code == "mixed_context_unsupported"


def test_publish_orchestration_maps_validation_issues():
    class FakeIssue:
        severity = "ERROR"
        object_type = "metric"
        object_key = "total_revenue"
        code = "COLUMN_NOT_FOUND"
        message = "Column net_sales no longer exists."
        category = "SOURCE"

    class FakeValidation:
        valid = False
        errors = [FakeIssue()]
        warnings = []

    issues = SemanticPublishOrchestrationService._issues_from_validation(FakeValidation())
    assert len(issues) == 1
    assert issues[0].code == "COLUMN_NOT_FOUND"
