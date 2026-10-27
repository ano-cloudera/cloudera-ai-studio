from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.chat.context_sources import ContextSourceError, context_source_http_error
from app.core.models import AskDataRequest, AskDataResponse
from app.llm.registry import ProviderSelectionError


router = APIRouter()
HEARTBEAT_SECONDS = 15
_SESSION_ID_MAX_LEN = 128


def _validate_selection(request: Request, body: AskDataRequest) -> None:
    try:
        request.app.state.provider_registry.resolve(body.provider, body.model)
    except ProviderSelectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/chat/sessions/{session_id}")
async def delete_chat_session(request: Request, session_id: str) -> dict[str, int]:
    cleaned = (session_id or "").strip()
    if not cleaned or len(cleaned) > _SESSION_ID_MAX_LEN:
        raise HTTPException(status_code=400, detail="Invalid session id")
    deleted = request.app.state.chat_service.delete_session_history(cleaned)
    return {"deleted": deleted}


@router.post("/chat", response_model=AskDataResponse)
async def chat(request: Request, body: AskDataRequest) -> AskDataResponse:
    try:
        body = request.app.state.chat_service.normalize_request(body)
    except ContextSourceError as exc:
        raise context_source_http_error(exc) from exc
    _validate_selection(request, body)
    return await request.app.state.chat_service.run(body)


@router.post("/chat/stream")
async def chat_stream(request: Request, body: AskDataRequest) -> StreamingResponse:
    try:
        body = request.app.state.chat_service.normalize_request(body)
    except ContextSourceError as exc:
        raise context_source_http_error(exc) from exc
    _validate_selection(request, body)

    async def events():
        iterator = request.app.state.chat_service.stream(body).__aiter__()
        pending = asyncio.create_task(iterator.__anext__())
        try:
            while True:
                done, _ = await asyncio.wait({pending}, timeout=HEARTBEAT_SECONDS)
                if not done:
                    yield ": keep-alive\n\n"
                    continue
                try:
                    event = pending.result()
                except StopAsyncIteration:
                    return
                payload = event.model_dump(mode="json") if hasattr(event, "model_dump") else event
                if isinstance(payload, dict) and hasattr(payload.get("response"), "model_dump"):
                    payload = {**payload, "response": payload["response"].model_dump(mode="json")}
                yield "data: " + json.dumps(payload, ensure_ascii=False, default=str) + "\n\n"
                pending = asyncio.create_task(iterator.__anext__())
        finally:
            if not pending.done():
                pending.cancel()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
