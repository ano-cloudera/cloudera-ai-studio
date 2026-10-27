from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.deps import default_project_context, postgres_session, require_postgres_settings
from app.core.config import Settings
from app.retrieval.schemas import RetrievalSearchRequest
from app.services.retrieval_service import RetrievalService, RetrievalServiceError

router = APIRouter(prefix="/retrieval", tags=["retrieval"])


def _handle_error(exc: RetrievalServiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


@router.post("/search")
def retrieval_search(
    body: RetrievalSearchRequest,
    session: Session = Depends(postgres_session),
    settings: Settings = Depends(require_postgres_settings),
    ctx=Depends(default_project_context),
) -> dict:
    workspace_id, default_project_id = ctx
    project_id = body.project_id or default_project_id
    if body.project_id and body.project_id != default_project_id:
        # M2C pilot: single default project — reject cross-project retrieval attempts.
        raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "Project access denied"})

    service = RetrievalService(settings, session)
    try:
        return service.retrieve(
            query=body.query,
            workspace_id=uuid.UUID(str(workspace_id)),
            project_id=uuid.UUID(str(project_id)),
            library_ids=body.library_ids,
            document_ids=body.document_ids,
            top_k=body.top_k,
        )
    except RetrievalServiceError as exc:
        raise _handle_error(exc) from exc
