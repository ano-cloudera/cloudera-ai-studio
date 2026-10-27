from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.config import Settings
from app.core.models import AskDataResponse


logger = logging.getLogger(__name__)


class LocalAgentError(Exception):
    """Any failure calling the TEMPO Local Agent fallback - always caught by
    the workflow node, never allowed to fail the overall request."""

    def __init__(self, code: str, *, http_status: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.http_status = http_status


_RETRYABLE_HTTP_STATUS = frozenset({429, 500, 502, 503, 504})


def _is_retryable_local_agent_failure(error: LocalAgentError) -> bool:
    if error.code == "NO_ANSWER" or error.code == "LOCAL_AGENT_DISABLED":
        return False
    if error.code == "HTTP_ERROR":
        return error.http_status in _RETRYABLE_HTTP_STATUS
    return error.code in {"TIMEOUT", "REQUEST_FAILED"}


class LocalAgentClient:
    """Thin client for the separately deployed TEMPO Local Agent REST API
    (reference/tempo-agent-api). Used only as a last-resort fallback when
    our own OSSIE planner reports strategy=unsupported - this system has
    its own independent governed KPI catalog (SQL always comes from a
    registered query_id, never LLM-generated - see that repo's
    tools.py/impala_runner.py), so a successful call here is still a
    governed answer, just from a second, separate catalog that may not
    agree 1:1 with ours. Callers must label the result as exploratory
    rather than presenting it with the same confidence as our own governed
    path.
    """

    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.base_url = settings.local_agent_base_url.rstrip("/")
        self.timeout = settings.local_agent_timeout_seconds
        self.engine = settings.local_agent_engine
        self.primary = settings.local_agent_primary
        self.max_attempts = settings.local_agent_max_attempts
        self.retry_delay_seconds = settings.local_agent_retry_delay_seconds
        self.transport = transport

    @property
    def enabled(self) -> bool:
        return bool(self.base_url)

    def _httpx_timeout(self) -> httpx.Timeout:
        return httpx.Timeout(connect=15.0, read=float(self.timeout), write=30.0, pool=15.0)

    def _ask_data_body(
        self,
        question: str,
        *,
        session_id: str,
        provider: str,
        model: str,
        request_id: str,
        answer_language: str = "id",
    ) -> dict[str, Any]:
        return {
            "question": question,
            "session_id": session_id,
            "provider": provider,
            "model": model,
            "request_id": request_id,
            "answer_language": answer_language,
            "engine": self.engine,
        }

    async def query(self, question: str, *, answer_language: str = "id") -> dict[str, Any]:
        if not self.enabled:
            raise LocalAgentError("LOCAL_AGENT_DISABLED")
        body = {
            "request_text": question,
            "engine": self.engine,
            "format": "json",
            "answer_language": answer_language,
        }
        last_error: LocalAgentError | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                payload = await self._post_query(body)
            except LocalAgentError as exc:
                last_error = exc
                if attempt >= self.max_attempts or not _is_retryable_local_agent_failure(exc):
                    raise
                logger.info(
                    "local_agent_retry attempt=%d/%d reason=%s http_status=%s",
                    attempt,
                    self.max_attempts,
                    exc.code,
                    exc.http_status,
                )
                if self.retry_delay_seconds:
                    await asyncio.sleep(self.retry_delay_seconds)
                continue

            status = str(payload.get("status") or "")
            if status in {"refused", "intent_unavailable", "grain_unavailable"} or not payload.get(
                "final_response_markdown"
            ):
                raise LocalAgentError("NO_ANSWER")
            return payload

        if last_error is not None:
            raise last_error
        raise LocalAgentError("REQUEST_FAILED")

    async def ask_data(
        self,
        question: str,
        *,
        session_id: str,
        provider: str,
        model: str,
        request_id: str,
        answer_language: str = "id",
    ) -> AskDataResponse:
        body = self._ask_data_body(
            question,
            session_id=session_id,
            provider=provider,
            model=model,
            request_id=request_id,
            answer_language=answer_language,
        )
        payload = await self._post_json("/v1/ask-data", body)
        return AskDataResponse.model_validate(payload)

    async def stream_ask_data(
        self,
        question: str,
        *,
        session_id: str,
        provider: str,
        model: str,
        request_id: str,
        answer_language: str = "id",
    ) -> AsyncIterator[dict[str, Any]]:
        body = self._ask_data_body(
            question,
            session_id=session_id,
            provider=provider,
            model=model,
            request_id=request_id,
            answer_language=answer_language,
        )
        try:
            async with httpx.AsyncClient(timeout=self._httpx_timeout(), transport=self.transport) as client:
                async with client.stream("POST", f"{self.base_url}/v1/ask-data/stream", json=body) as response:
                    response.raise_for_status()
                    buffer = ""
                    async for chunk in response.aiter_text():
                        buffer += chunk
                        while "\n\n" in buffer:
                            block, buffer = buffer.split("\n\n", 1)
                            for line in block.splitlines():
                                if not line.startswith("data:"):
                                    continue
                                raw = line[5:].strip()
                                if not raw:
                                    continue
                                try:
                                    event = json.loads(raw)
                                except json.JSONDecodeError:
                                    continue
                                if isinstance(event, dict):
                                    yield event
        except httpx.TimeoutException as exc:
            raise LocalAgentError("TIMEOUT") from exc
        except httpx.HTTPStatusError as exc:
            raise LocalAgentError("HTTP_ERROR", http_status=exc.response.status_code) from exc
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            raise LocalAgentError("REQUEST_FAILED") from exc

    async def _post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self._httpx_timeout(), transport=self.transport) as client:
                response = await client.post(f"{self.base_url}{path}", json=body)
                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException as exc:
            raise LocalAgentError("TIMEOUT") from exc
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "local_agent_http_error status=%s endpoint=%s",
                exc.response.status_code,
                exc.request.url.path,
            )
            raise LocalAgentError("HTTP_ERROR", http_status=exc.response.status_code) from exc
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            raise LocalAgentError("REQUEST_FAILED") from exc

    async def _post_query(self, body: dict[str, Any]) -> dict[str, Any]:
        return await self._post_json("/v1/query", body)


_HEADING_RE = re.compile(r"^#+\s*", re.MULTILINE)


def markdown_to_plain_answer(markdown: str) -> str:
    """Reduce the local agent's Markdown answer (## Answer / ## Routing
    sections, tables) to the first prose section for direct_answer /
    executive_summary - the routing/candidate table is internal detail our
    own AnalysisOutput schema has no field for, and stays out of the
    business-facing answer text."""
    text = markdown.split("## Routing")[0]
    text = _HEADING_RE.sub("", text).strip()
    # Drop a trailing "---" section divider some responses include.
    text = re.sub(r"\n-{3,}\s*$", "", text).strip()
    return text or markdown.strip()
