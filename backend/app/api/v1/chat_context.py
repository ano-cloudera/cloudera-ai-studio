from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import default_project_context, postgres_session
from app.services.context_picker_options_service import ContextPickerOptionsService

router = APIRouter(prefix="/chat", tags=["chat-context"])


@router.get("/context-options")
def list_context_options(
    session: Session = Depends(postgres_session),
    ctx=Depends(default_project_context),
    search: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
):
    ws, proj = ctx[0], ctx[1]
    return ContextPickerOptionsService(session).list_options(
        workspace_id=ws,
        project_id=proj,
        search=search,
        limit=limit,
    )
