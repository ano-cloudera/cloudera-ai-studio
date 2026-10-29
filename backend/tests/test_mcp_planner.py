from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from app.llm.base import ProviderError
from app.mcp.planner import (
    McpNarration,
    McpToolPlan,
    PlannedCall,
    build_planned_call,
    missing_inputs_message,
    narrate_result,
    plan_tool_call,
    tool_descriptors,
)

SCHEMA = {
    "type": "object",
    "properties": {
        "credit_score": {"type": "integer", "description": "Bureau-style score, 300-850."},
        "dti_ratio": {"type": "number", "description": "Debt-to-income as a fraction."},
        "requested_amount": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "region_name": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "required": ["credit_score", "dti_ratio"],
}


def _tool(schema_attr: str = "inputSchema"):
    return SimpleNamespace(name="assess_application_risk", description="Score it.", **{schema_attr: SCHEMA})


def test_descriptors_read_both_schema_attribute_names() -> None:
    assert tool_descriptors([_tool("inputSchema")])[0]["input_schema"] == SCHEMA
    assert tool_descriptors([_tool("input_schema")])[0]["input_schema"] == SCHEMA
    assert tool_descriptors([{"name": "t", "inputSchema": SCHEMA}])[0]["input_schema"] == SCHEMA


def test_arguments_are_coerced_filtered_and_missing_ones_reported() -> None:
    descriptors = tool_descriptors([_tool()])
    plan = McpToolPlan(
        tool="assess_application_risk",
        arguments_json=json.dumps(
            {"credit_score": "640", "requested_amount": "150,000,000", "region_name": " Jawa Barat ", "invented": 1}
        ),
    )
    call = build_planned_call(plan, descriptors)
    assert call.arguments == {"credit_score": 640, "requested_amount": 150000000.0, "region_name": "Jawa Barat"}
    assert call.missing == ["dti_ratio"]  # required, not said by the user


def test_a_model_claiming_nothing_is_missing_cannot_hide_a_missing_required_argument() -> None:
    call = build_planned_call(
        McpToolPlan(tool="assess_application_risk", arguments_json="{}", missing=[]), tool_descriptors([_tool()])
    )
    assert call.missing == ["credit_score", "dti_ratio"]


def test_bad_json_and_unknown_tool_degrade_safely() -> None:
    call = build_planned_call(McpToolPlan(tool="nope", arguments_json="not json"), tool_descriptors([_tool()]))
    assert call.tool == "assess_application_risk"
    assert call.arguments == {}


class _Provider:
    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.messages: list = []

    async def generate_structured(self, messages, response_model, *, temperature, max_tokens):
        self.messages.append(messages)
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


def test_plan_tool_call_sends_the_schema_and_returns_a_checked_call() -> None:
    provider = _Provider(
        McpToolPlan(tool="assess_application_risk", arguments_json='{"credit_score": 640, "dti_ratio": 0.4}')
    )
    call = asyncio.run(plan_tool_call(provider, "score 640 with dti 0.40", [_tool()]))
    assert call is not None and call.arguments == {"credit_score": 640, "dti_ratio": 0.4} and not call.missing
    payload = json.loads(provider.messages[0][1]["content"])
    assert payload["tools"][0]["input_schema"] == SCHEMA


def test_narration_falls_back_to_none_when_the_model_fails() -> None:
    ok = asyncio.run(narrate_result(_Provider(McpNarration(answer="  Low likelihood.  ")), "q", "t", {}, "{}"))
    assert ok == "Low likelihood."
    failed = asyncio.run(narrate_result(_Provider(ProviderError("X")), "q", "t", {}, "{}"))
    assert failed is None


def test_missing_inputs_message_follows_the_language_of_the_question() -> None:
    call = PlannedCall(
        tool="t",
        arguments={},
        missing=["dti_ratio"],
        descriptions={"dti_ratio": "Debt-to-income as a fraction. 0.40 means 40 percent."},
    )
    english = missing_inputs_message(call, "Assess an applicant with credit score 640")
    assert english.startswith("To run this assessment I still need:")
    assert "- dti ratio: Debt-to-income as a fraction" in english
    assert missing_inputs_message(call, "Tolong nilai pemohon dengan skor 640").startswith("Untuk menjalankan")
