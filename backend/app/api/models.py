from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.models import ModelList


router = APIRouter()


@router.get("/models", response_model=ModelList)
def models(request: Request) -> ModelList:
    return ModelList(models=request.app.state.provider_registry.list_models())
