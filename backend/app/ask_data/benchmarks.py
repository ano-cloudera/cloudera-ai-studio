"""Run example questions through Ask Data and compare the answer with the number the team expects."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from app.core.models import AskDataRequest, AskDataResponse, ChatContextSource
from app.workspace.semantic_knowledge import BenchmarkRun, ExampleQuestion


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_value(response: AskDataResponse, match: str | None) -> float | None:
    """The metric figure of the row the example points at: the row containing `match`, else the first row."""
    rows = response.data.rows or []
    if not rows:
        return None
    row = rows[0]
    if match:
        needle = match.casefold()
        found = next((r for r in rows if any(needle in str(v).casefold() for v in r.values() if isinstance(v, str))), None)
        if found is None:
            return None
        row = found
    if "metric_value" in row:
        return _number(row["metric_value"])
    return next((n for n in (_number(v) for v in row.values()) if n is not None), None)


def judge_example(example: ExampleQuestion, response: AskDataResponse | None, error: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"question": example.question, "expected": example.expected_value, "tolerance": example.tolerance, "match": example.match}
    if response is None:
        return {**result, "status": "error", "actual": None, "message": error or "The question could not be answered."}
    actual = extract_value(response, example.match)
    result.update({"actual": actual, "answer": response.answer.direct_answer, "sql": response.governed_sql})
    if example.expected_value is None:
        return {**result, "status": "answered" if response.status == "SUCCESS" else "error", "message": "No expected value to compare."}
    if response.status != "SUCCESS":
        return {**result, "status": "error", "message": f"Ask Data returned {response.status}."}
    if actual is None:
        return {**result, "status": "fail", "message": "No matching value in the result."}
    ok = abs(actual - example.expected_value) <= example.tolerance
    return {**result, "status": "pass" if ok else "fail", "message": "" if ok else f"Expected {example.expected_value:g}, got {actual:g}."}


async def run_examples(
    chat_service: Any,
    *,
    examples: list[ExampleQuestion],
    provider: str,
    model: str,
    semantic_model: tuple[str, str] | None = None,
) -> list[dict[str, Any]]:
    """One question at a time, each in its own throw-away session."""
    results: list[dict[str, Any]] = []
    for example in examples:
        started = perf_counter()
        request = AskDataRequest(
            session_id=f"benchmark-{uuid.uuid4()}",
            question=example.question,
            provider=provider,  # type: ignore[arg-type]
            model=model,
            context_sources=[ChatContextSource(type="semantic_model", id=semantic_model[0], name=semantic_model[1])] if semantic_model else None,
        )
        try:
            request = chat_service.normalize_request(request)
            response = await chat_service.run(request)
            result = judge_example(example, response)
        except Exception as exc:  # noqa: BLE001 - one failing question must not stop the run
            result = judge_example(example, None, error=str(exc)[:200])
        results.append({**result, "ms": round((perf_counter() - started) * 1000)})
    return results


def summarize_run(results: list[dict[str, Any]], published_version: int | None) -> BenchmarkRun:
    checked = [r for r in results if r.get("expected") is not None]
    return BenchmarkRun(
        at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        published_version=published_version,
        passed=sum(1 for r in checked if r["status"] == "pass"),
        total=len(checked),
    )
