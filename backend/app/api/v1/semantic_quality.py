"""Instructions, example questions and benchmark runs for one semantic model."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import default_project_context, postgres_session
from app.ask_data.benchmarks import run_examples, summarize_run
from app.core.models import StrictModel
from app.db.platform_models import SemanticModelRow, SemanticVersionRow, WorkspaceRow
from app.workspace.semantic_knowledge import (
    MAX_RUNS,
    ExampleQuestion,
    SemanticKnowledge,
    read_semantic_knowledge,
    write_semantic_knowledge,
)

router = APIRouter(prefix="/semantic/models/{model_id}", tags=["semantic"])


class KnowledgeBody(StrictModel):
    instructions: str = ""
    examples: list[ExampleQuestion] = []


class BenchmarkRunBody(StrictModel):
    provider: str
    model: str


def _load(session: Session, ctx, model_id: uuid.UUID) -> tuple[WorkspaceRow, SemanticModelRow]:
    ws, proj = ctx[0], ctx[1]
    model = session.get(SemanticModelRow, model_id)
    if model is None or model.workspace_id != ws or model.project_id != proj:
        raise HTTPException(status_code=404, detail={"code": "MODEL_NOT_FOUND", "message": "Semantic model not found"})
    workspace = session.get(WorkspaceRow, ws)
    if workspace is None:
        raise HTTPException(status_code=404, detail={"code": "WORKSPACE_NOT_FOUND", "message": "Workspace not found"})
    return workspace, model


@router.get("/knowledge")
def get_knowledge(model_id: uuid.UUID, session: Session = Depends(postgres_session), ctx=Depends(default_project_context)) -> dict:
    workspace, _ = _load(session, ctx, model_id)
    return read_semantic_knowledge(workspace.settings_json, str(model_id)).model_dump()


@router.put("/knowledge")
def put_knowledge(model_id: uuid.UUID, body: KnowledgeBody, session: Session = Depends(postgres_session), ctx=Depends(default_project_context)) -> dict:
    """Replace the instructions and examples; the run history is kept."""
    workspace, _ = _load(session, ctx, model_id)
    current = read_semantic_knowledge(workspace.settings_json, str(model_id))
    updated = SemanticKnowledge(instructions=body.instructions.strip(), examples=body.examples, runs=current.runs)
    workspace.settings_json = write_semantic_knowledge(workspace.settings_json, str(model_id), updated)
    session.add(workspace)
    session.commit()
    return updated.model_dump()


@router.post("/benchmarks/run")
async def run_benchmarks(
    model_id: uuid.UUID,
    body: BenchmarkRunBody,
    request: Request,
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
) -> dict:
    """Ask every example that has an expected value and report pass or fail; the score is stored with the published version."""
    workspace, model = _load(session, ctx, model_id)
    knowledge = read_semantic_knowledge(workspace.settings_json, str(model_id))
    checked = [e for e in knowledge.examples if e.expected_value is not None]
    if not checked:
        raise HTTPException(status_code=422, detail={"code": "NO_BENCHMARKS", "message": "Add at least one example question with an expected value."})
    if model.active_version_id is None:
        raise HTTPException(status_code=409, detail={"code": "NOT_PUBLISHED", "message": "Publish the model first: benchmarks run against the published version."})
    version = session.get(SemanticVersionRow, model.active_version_id)
    results = await run_examples(
        request.app.state.chat_service,
        examples=checked,
        provider=body.provider,
        model=body.model,
        semantic_model=(str(model.id), model.name),
    )
    run = summarize_run(results, version.version_number if version else None)
    updated = knowledge.model_copy(update={"runs": [run, *knowledge.runs][:MAX_RUNS]})
    workspace.settings_json = write_semantic_knowledge(workspace.settings_json, str(model_id), updated)
    session.add(workspace)
    session.commit()
    return {"run": run.model_dump(), "results": results, "runs": [r.model_dump() for r in updated.runs]}
