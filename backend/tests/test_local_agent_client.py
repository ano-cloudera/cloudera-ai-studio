from __future__ import annotations

import httpx
import pytest

from app.services.local_agent_client import LocalAgentClient, LocalAgentError, markdown_to_plain_answer

from conftest import isolated_settings


def _settings(**overrides):
    return isolated_settings(local_agent_base_url="http://local-agent.internal", **overrides)


def test_client_is_disabled_when_base_url_is_empty() -> None:
    client = LocalAgentClient(isolated_settings(local_agent_base_url=""))
    assert client.enabled is False


@pytest.mark.asyncio
async def test_disabled_client_raises_without_making_a_request() -> None:
    client = LocalAgentClient(isolated_settings(local_agent_base_url=""))
    with pytest.raises(LocalAgentError):
        await client.query("Berapa gross sales?")


@pytest.mark.asyncio
async def test_successful_query_returns_the_raw_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/query"
        return httpx.Response(
            200,
            json={
                "status": "pareto",
                "resolved_query_ids": ["SI-01@calquarter_material"],
                "final_response_markdown": "## Answer\n\nTop 5 produk...\n\n## Routing\n\n(details)",
            },
        )

    client = LocalAgentClient(_settings(), transport=httpx.MockTransport(handler))
    payload = await client.query("Top 5 produk dengan sell-in tertinggi")

    assert payload["resolved_query_ids"] == ["SI-01@calquarter_material"]


@pytest.mark.asyncio
async def test_refusal_status_raises_local_agent_error_instead_of_returning_a_non_answer() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "intent_unavailable",
                "resolved_query_ids": [],
                "final_response_markdown": "## Answer\n\nI could not match your question...",
            },
        )

    client = LocalAgentClient(_settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(LocalAgentError):
        await client.query("Top 5 widgets with flarn coefficient")


@pytest.mark.asyncio
async def test_timeout_raises_local_agent_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    client = LocalAgentClient(_settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(LocalAgentError):
        await client.query("Berapa gross sales?")


@pytest.mark.asyncio
async def test_http_error_raises_local_agent_error() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500, json={"error": "agent_failed"})

    client = LocalAgentClient(
        _settings(local_agent_max_attempts=2, local_agent_retry_delay_seconds=0),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(LocalAgentError, match="HTTP_ERROR"):
        await client.query("Berapa gross sales?")
    assert calls == 2


@pytest.mark.asyncio
async def test_retryable_http_error_succeeds_on_second_attempt() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, json={"error": "busy"})
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "resolved_query_ids": ["PK-01"],
                "final_response_markdown": "## Answer\n\nFill rate cabang A: 92%.",
            },
        )

    client = LocalAgentClient(
        _settings(local_agent_max_attempts=2, local_agent_retry_delay_seconds=0),
        transport=httpx.MockTransport(handler),
    )
    payload = await client.query("Fill rate cabang")
    assert payload["resolved_query_ids"] == ["PK-01"]
    assert calls == 2


@pytest.mark.asyncio
async def test_refusal_does_not_retry() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "status": "intent_unavailable",
                "resolved_query_ids": [],
                "final_response_markdown": "## Answer\n\nNo match.",
            },
        )

    client = LocalAgentClient(
        _settings(local_agent_max_attempts=3, local_agent_retry_delay_seconds=0),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(LocalAgentError, match="NO_ANSWER"):
        await client.query("Unknown metric")
    assert calls == 1


def test_markdown_to_plain_answer_strips_routing_section_and_headings() -> None:
    markdown = (
        "## Answer\n\nTotal Gross Sell In adalah Rp 3,84 triliun.\n\n"
        "| Gross Bill Val (IDR) |\n|---:|\n| 3.841.865.787.074 |\n---\n\n"
        "## Routing\n\n**Candidates considered**\n\n| # | Measure |\n| --- | --- |\n| 1 | SI-01 |"
    )
    result = markdown_to_plain_answer(markdown)
    assert "Total Gross Sell In" in result
    assert "Routing" not in result
    assert "Candidates considered" not in result


def test_markdown_to_plain_answer_falls_back_to_raw_text_when_no_sections_match() -> None:
    assert markdown_to_plain_answer("Just plain text, no headings at all.") == "Just plain text, no headings at all."


@pytest.mark.asyncio
async def test_ask_data_uses_v3_contract_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/ask-data"
        return httpx.Response(
            200,
            json={
                "request_id": "r1",
                "session_id": "s1",
                "status": "SUCCESS",
                "provider": "openai",
                "model": "tempo-agent-v3",
                "strategy": "governed",
                "answer": {
                    "direct_answer": "OK",
                    "executive_summary": "OK",
                    "insights": [],
                    "business_implications": [],
                    "caveats": [],
                    "data_reference": "ID-02@dcname",
                    "chart_spec": None,
                },
                "data": {"columns": [], "rows": [], "row_count": 0, "execution_ms": 0},
                "chart_spec": None,
                "timings": {"total_ms": 1},
                "retry_count": 0,
            },
        )

    client = LocalAgentClient(_settings(local_agent_primary=True), transport=httpx.MockTransport(handler))
    response = await client.ask_data(
        "Top DC stok",
        session_id="s1",
        provider="openai",
        model="tempo-agent-v3",
        request_id="r1",
    )
    assert response.strategy == "governed"
