"""The demo credit-risk MCP server: scoring, the stdio tool, and a full turn through the planner."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "mcp"
sys.path.insert(0, str(SCRIPTS))

from credit_risk_scoring import assess  # noqa: E402

from app.mcp import service  # noqa: E402
from app.mcp.client import invoke_mcp_server  # noqa: E402
from app.mcp.planner import McpNarration, McpToolPlan, PlannedCall  # noqa: E402
from app.workspace.mcp_settings import McpServerEntry  # noqa: E402

pytest.importorskip("mcp")


def test_policy_check_follows_the_documented_thresholds() -> None:
    ok = assess(720, 0.30)
    assert ok["policy_check"]["meets_standard_criteria"] is True
    assert ok["policy_check"]["policy_exception_required_for_approval"] is False
    assert ok["likelihood_band"] == "High"

    low_score = assess(640, 0.40)
    assert low_score["policy_check"]["credit_score"]["ok"] is False
    assert low_score["policy_check"]["dti_ratio"]["ok"] is True
    assert low_score["policy_check"]["policy_exception_required_for_approval"] is True
    assert low_score["likelihood_band"] == "Low"


def test_likelihood_rises_with_score_and_falls_with_dti() -> None:
    assert assess(700, 0.30)["approval_likelihood"] > assess(640, 0.30)["approval_likelihood"]
    assert assess(700, 0.30)["approval_likelihood"] > assess(700, 0.50)["approval_likelihood"]


def test_never_claims_certainty_and_never_returns_a_verdict() -> None:
    result = assess(850, 0.05)
    assert 0.001 <= result["approval_likelihood"] <= 0.999
    assert not {"decision", "verdict", "approved", "rejected"} & set(result)
    assert "human reviewer" in result["guardrail"]


def test_dti_given_as_a_percentage_is_read_as_a_fraction() -> None:
    assert assess(700, 40)["inputs_used"]["dti_ratio"] == 0.4


def test_unknown_categories_are_ignored_not_guessed() -> None:
    result = assess(700, 0.3, application_channel="Telepathy", region_name="jawa barat")
    assert result["inputs_used"].get("region_name") == "Jawa Barat"
    assert "application_channel" not in result["inputs_used"]


@pytest.mark.parametrize(
    "kwargs",
    [{"credit_score": 900, "dti_ratio": 0.4}, {"credit_score": 700, "dti_ratio": 0}, {"credit_score": 700, "dti_ratio": 0.4, "requested_amount": -1}],
)
def test_invalid_inputs_are_rejected(kwargs) -> None:
    with pytest.raises(ValueError):
        assess(**kwargs)


def _entry() -> McpServerEntry:
    return McpServerEntry(
        id="credit-risk", name="Credit Risk Model", transport="stdio",
        command=sys.executable, args=[str(SCRIPTS / "credit_risk_server.py")],
    )


def test_the_real_stdio_server_scores_through_the_client() -> None:
    async def planner(tools, question):
        return PlannedCall(
            tool="assess_application_risk",
            arguments={"credit_score": 640, "dti_ratio": 0.4, "region_name": "Jawa Barat"},
        )

    result = asyncio.run(invoke_mcp_server(_entry(), question="x", planner=planner))
    payload = json.loads(result["content"])
    assert payload["policy_check"]["policy_exception_required_for_approval"] is True
    assert result["tool"] == "assess_application_risk"


def test_missing_required_inputs_are_returned_without_calling_the_tool() -> None:
    async def planner(tools, question):
        return PlannedCall(tool="assess_application_risk", arguments={"credit_score": 640}, missing=["dti_ratio"])

    result = asyncio.run(invoke_mcp_server(_entry(), question="x", planner=planner))
    assert result["missing"] == ["dti_ratio"] and result["content"] == ""


class _Provider:
    def __init__(self, *outputs):
        self.outputs = list(outputs)

    async def generate_structured(self, messages, response_model, *, temperature, max_tokens):
        return self.outputs.pop(0)


def _patch_registry(monkeypatch) -> None:
    monkeypatch.setattr(service, "connector_by_id", lambda *a, **k: SimpleNamespace(name="Credit Risk Model"))
    monkeypatch.setattr(service, "resolve_server_entry", lambda *a, **k: _entry())


def test_a_full_turn_plans_calls_the_model_and_narrates(monkeypatch) -> None:
    _patch_registry(monkeypatch)
    provider = _Provider(
        McpToolPlan(tool="assess_application_risk", arguments_json='{"credit_score": 640, "dti_ratio": 0.4}'),
        McpNarration(answer="The approval likelihood is about 16%, which is low."),
    )
    answer, meta = asyncio.run(
        service.run_mcp_turn(
            SimpleNamespace(), workspace_settings_json=None, connector_id="credit-risk",
            question="Assess an applicant with credit score 640 and DTI 0.40", provider=provider,
        )
    )
    assert answer == "The approval likelihood is about 16%, which is low."
    assert meta["arguments"] == {"credit_score": 640, "dti_ratio": 0.4}


def test_a_turn_with_missing_inputs_asks_for_them(monkeypatch) -> None:
    _patch_registry(monkeypatch)
    provider = _Provider(McpToolPlan(tool="assess_application_risk", arguments_json='{"credit_score": 640}'))
    answer, meta = asyncio.run(
        service.run_mcp_turn(
            SimpleNamespace(), workspace_settings_json=None, connector_id="credit-risk",
            question="Assess an applicant with credit score 640", provider=provider,
        )
    )
    assert "I still need" in answer and "dti ratio" in answer
    assert meta["missing"] == ["dti_ratio"]


def test_without_a_model_the_raw_result_is_still_shown(monkeypatch) -> None:
    _patch_registry(monkeypatch)
    answer, _ = asyncio.run(
        service.run_mcp_turn(
            SimpleNamespace(), workspace_settings_json=None, connector_id="credit-risk",
            question="credit score 640 dti 0.4", provider=None,
        )
    )
    # No planner: the old behavior sends the raw question text, so the tool reports the unusable input.
    assert answer.startswith("**MCP (Credit Risk Model)**")


def test_a_missing_server_script_is_reported_plainly() -> None:
    from app.mcp.client import probe_mcp_server, stdio_preflight_problem

    entry = McpServerEntry(
        id="x", name="X", transport="stdio", command=sys.executable,
        args=["/home/cdsw/cloudera-ai-studio/scripts/mcp/credit_risk_server."],
    )
    entry.args = ["/nonexistent/credit_risk_server.py"]
    assert stdio_preflight_problem(entry) == "Server script not found: /nonexistent/credit_risk_server.py"
    probe = asyncio.run(probe_mcp_server(entry))
    assert probe["ok"] is False and probe["message"].startswith("Server script not found")


def test_a_missing_command_is_reported_plainly() -> None:
    from app.mcp.client import stdio_preflight_problem

    entry = McpServerEntry(id="x", name="X", transport="stdio", command="/nonexistent/python", args=[])
    assert stdio_preflight_problem(entry) == "Command not found: /nonexistent/python"


def test_exception_groups_are_unwrapped_to_the_real_cause() -> None:
    from exceptiongroup import ExceptionGroup  # Python 3.10 has no builtin; anyio and mcp depend on this backport

    from app.mcp.client import describe_exception

    group = ExceptionGroup("unhandled errors in a TaskGroup", [FileNotFoundError("no such file"), ValueError("boom")])
    assert describe_exception(group) == "no such file; boom"


def test_the_real_server_still_connects_after_the_preflight() -> None:
    from app.mcp.client import probe_mcp_server

    probe = asyncio.run(probe_mcp_server(_entry()))
    assert probe["ok"] is True and "assess_application_risk" in probe["tools"]
