from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.chat.context_sources import ContextSourceError, context_source_http_error
from app.ask_data.agent_mode import AskDataAgent
from app.core.language import detect_language
from app.core.models import AskDataRequest, AskDataResponse
from app.llm.registry import ProviderSelectionError


router = APIRouter()
HEARTBEAT_SECONDS = 15
_SESSION_ID_MAX_LEN = 128


def _validate_selection(request: Request, body: AskDataRequest) -> None:
    if request.app.state.chat_service.assigned_model(body.mode) is not None:
        return  # the assigned model runs instead of the one sent; a broken assignment is reported when it runs
    try:
        request.app.state.provider_registry.resolve(body.provider, body.model)
    except ProviderSelectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _language(body: AskDataRequest) -> str:
    return "id" if detect_language(body.question) == "id" else "en"


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
    if body.mode != "mcp":
        _validate_selection(request, body)
    agent = AskDataAgent(request.app.state.chat_service)
    if agent.applicable(body):
        answered = await agent.run(body)
        if answered is not None:
            return answered.model_copy(update={"language": _language(body)})
    response = await request.app.state.chat_service.run(body)
    return response.model_copy(update={"language": _language(body)})


@router.post("/chat/stream")
async def chat_stream(request: Request, body: AskDataRequest) -> StreamingResponse:
    try:
        body = request.app.state.chat_service.normalize_request(body)
    except ContextSourceError as exc:
        raise context_source_http_error(exc) from exc
    if body.mode != "mcp":
        _validate_selection(request, body)

    async def events():
        # One task drives the whole generator: context variables set in an early step (the model
        # registry resolution) must still be visible in later steps, which separate tasks per step lose.
        queue: asyncio.Queue = asyncio.Queue()
        done_marker = object()

        async def produce() -> None:
            try:
                finished = False
                async for event in AskDataAgent(request.app.state.chat_service).stream(body):
                    finished = finished or event.get("type") == "done"
                    await queue.put(event)
                if finished:
                    return  # the agent answered; otherwise the normal pipeline below does
                async for event in request.app.state.chat_service.stream(body):
                    await queue.put(event)
            except BaseException as exc:  # noqa: BLE001 - forwarded to the consumer
                await queue.put(exc)
            finally:
                await queue.put(done_marker)

        producer = asyncio.create_task(produce())
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                if event is done_marker:
                    return
                if isinstance(event, BaseException):
                    raise event
                payload = event.model_dump(mode="json") if hasattr(event, "model_dump") else event
                if isinstance(payload, dict) and hasattr(payload.get("response"), "model_dump"):
                    payload = {**payload, "response": {**payload["response"].model_dump(mode="json"), "language": _language(body)}}
                yield "data: " + json.dumps(payload, ensure_ascii=False, default=str) + "\n\n"
        finally:
            if not producer.done():
                producer.cancel()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
