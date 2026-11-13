"""Home dashboard: the headline KPIs of the published semantic model, their trend, breakdown and map, and a short briefing."""
from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request

from app.core.models import AskDataRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/home", tags=["home"])


def _request(request: Request, provider: str | None, model: str | None) -> AskDataRequest:
    """The model a briefing is written with: the one the browser chose, else the one assigned to Ask Data."""
    chat = request.app.state.chat_service
    if not (provider and model):
        assigned = chat.assigned_model("ask_data")
        if assigned is None:
            raise HTTPException(status_code=422, detail="Pass provider and model, or assign a model to Ask Data in Settings.")
        provider, model = assigned.provider, assigned.id
    if provider not in ("qwen", "gemini", "openai"):
        raise HTTPException(status_code=422, detail="Unknown provider")
    return AskDataRequest(session_id="home", question="home", provider=provider, model=model)  # type: ignore[arg-type]


@router.get("")
async def home(
    request: Request,
    provider: Literal["qwen", "gemini", "openai"] | None = None,
    model: str | None = Query(default=None, max_length=256),
    refresh: bool = False,
) -> dict:
    from app.home.dashboard import build_home

    return await build_home(request.app.state.chat_service, _request(request, provider, model), refresh=refresh)


@router.get("/briefing")
async def briefing(
    request: Request,
    provider: Literal["qwen", "gemini", "openai"] | None = None,
    model: str | None = Query(default=None, max_length=256),
    refresh: bool = False,
) -> dict:
    from app.home.dashboard import build_briefing

    try:
        return await build_briefing(request.app.state.chat_service, _request(request, provider, model), refresh=refresh)
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001 - Home shows its figures without a briefing
        logger.exception("home_briefing_failed")
        return {"status": "failed"}
