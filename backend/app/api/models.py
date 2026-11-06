from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.models import ModelList


router = APIRouter()


@router.get("/models", response_model=ModelList)
def models(request: Request) -> ModelList:
    listed = list(request.app.state.provider_registry.list_models())
    assigned = request.app.state.chat_service.assigned_model("ask_data")
    if assigned is not None:
        # The model assigned in Settings -> AI Models answers whatever the browser sends, so it is offered even when its
        # provider has no environment variables (a private vLLM Qwen registered only through the registry).
        listed = [assigned, *[item for item in listed if item.provider != assigned.provider]]
    return ModelList(models=listed)
