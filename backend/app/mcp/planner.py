"""Plan an MCP tool call from a question and explain the result (LLM-assisted, schema-checked).

The MCP client used to send the raw question text to the first tool. A tool with typed inputs (a model that needs
a credit score and a DTI ratio) needs real arguments, so the model reads the tool's input schema, fills the
arguments from the question, and anything required that the user did not say is reported back instead of invented.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import BACKEND_ROOT
from app.core.language import detect_language
from app.llm.base import LLMProvider, ProviderError

logger = logging.getLogger(__name__)

_PROMPT_DIR = BACKEND_ROOT / "prompts"


class McpToolPlan(BaseModel):
    tool: str
    arguments_json: str = "{}"
    missing: list[str] = Field(default_factory=list)


class McpNarration(BaseModel):
    answer: str


@dataclass
class PlannedCall:
    tool: str
    arguments: dict[str, Any]
    missing: list[str] = field(default_factory=list)
    descriptions: dict[str, str] = field(default_factory=dict)


def _field(tool: Any, *names: str) -> Any:
    for name in names:
        value = tool.get(name) if isinstance(tool, dict) else getattr(tool, name, None)
        if value:
            return value
    return None


def tool_descriptors(tools: list[Any]) -> list[dict[str, Any]]:
    """Name, description and input schema of each tool; mcp 1.x says inputSchema, 2.x says input_schema."""
    out: list[dict[str, Any]] = []
    for tool in tools:
        name = _field(tool, "name")
        if not name:
            continue
        schema = _field(tool, "inputSchema", "input_schema") or {}
        out.append(
            {
                "name": str(name),
                "description": str(_field(tool, "description") or "")[:1500],
                "input_schema": schema if isinstance(schema, dict) else {},
            }
        )
    return out


def _types(prop: dict[str, Any]) -> set[str]:
    declared = prop.get("type")
    found = {declared} if isinstance(declared, str) else set(declared or [])
    for option in prop.get("anyOf") or []:
        if isinstance(option, dict) and isinstance(option.get("type"), str):
            found.add(option["type"])
    found.discard("null")
    return found


def _coerce(value: Any, prop: dict[str, Any]) -> Any:
    kinds = _types(prop)
    try:
        if "integer" in kinds and "number" not in kinds:
            return int(round(float(str(value).replace(",", "").strip())))
        if "number" in kinds:
            return float(str(value).replace(",", "").strip())
        if "boolean" in kinds:
            return value if isinstance(value, bool) else str(value).strip().casefold() in {"true", "yes", "1"}
        if "string" in kinds:
            return str(value).strip()
    except (TypeError, ValueError):
        return None
    return value


def build_planned_call(plan: McpToolPlan, descriptors: list[dict[str, Any]]) -> PlannedCall:
    by_name = {d["name"]: d for d in descriptors}
    descriptor = by_name.get(plan.tool) or descriptors[0]
    schema = descriptor.get("input_schema") or {}
    properties: dict[str, Any] = schema.get("properties") or {}
    try:
        raw = json.loads(plan.arguments_json or "{}")
    except json.JSONDecodeError:
        raw = {}
    arguments: dict[str, Any] = {}
    for key, value in (raw if isinstance(raw, dict) else {}).items():
        if key not in properties or value is None or value == "":
            continue
        coerced = _coerce(value, properties[key])
        if coerced is not None:
            arguments[key] = coerced
    # Required arguments the user did not give are decided here, not by the model.
    missing = [name for name in schema.get("required") or [] if name not in arguments]
    return PlannedCall(
        tool=descriptor["name"],
        arguments=arguments,
        missing=missing,
        descriptions={k: str(v.get("description") or "") for k, v in properties.items() if isinstance(v, dict)},
    )


def _prompt(name: str) -> str:
    return (_PROMPT_DIR / name).read_text(encoding="utf-8")


async def plan_tool_call(provider: LLMProvider, question: str, tools: list[Any]) -> PlannedCall | None:
    descriptors = tool_descriptors(tools)
    if not descriptors:
        return None
    plan = await provider.generate_structured(
        [
            {"role": "system", "content": _prompt("mcp_tool_plan.md")},
            {"role": "user", "content": json.dumps({"question": question, "tools": descriptors}, ensure_ascii=False)},
        ],
        McpToolPlan,
        temperature=0,
        max_tokens=600,
    )
    return build_planned_call(plan, descriptors)


async def narrate_result(
    provider: LLMProvider, question: str, tool: str, arguments: dict[str, Any], content: str
) -> str | None:
    messages = [
        {"role": "system", "content": _prompt("mcp_answer.md")},
        {
            "role": "user",
            "content": json.dumps(
                {"question": question, "tool": tool, "arguments": arguments, "result": content[:6000]},
                ensure_ascii=False,
            ),
        },
    ]
    # A malformed or timed-out completion is common enough to deserve one more try.
    for attempt in (1, 2):
        try:
            out = await provider.generate_structured(
                messages, McpNarration, temperature=0.2 if attempt == 1 else 0, max_tokens=700
            )
        except ProviderError:
            logger.warning("mcp_narration_failed tool=%s attempt=%s", tool, attempt)
            continue
        if out.answer.strip():
            return out.answer.strip()
    return None


def _scalar_text(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def readable_result(content: str) -> str:
    """Plain bullets for a tool result when the model could not narrate it; never raw JSON."""
    try:
        data = json.loads(content)
    except (TypeError, ValueError):
        return content
    if not isinstance(data, dict):
        return content
    lines: list[str] = []
    for key, value in data.items():
        label = str(key).replace("_", " ")
        if isinstance(value, dict):
            parts = ", ".join(
                f"{str(k).replace('_', ' ')} {_scalar_text(v)}" for k, v in value.items() if not isinstance(v, (dict, list))
            )
            if parts:
                lines.append(f"- **{label}**: {parts}")
        elif isinstance(value, list):
            items = [_scalar_text(v) for v in value if not isinstance(v, (dict, list))]
            if items:
                lines.append(f"- **{label}**:")
                lines.extend(f"  - {item}" for item in items)
        else:
            lines.append(f"- **{label}**: {_scalar_text(value)}")
    return "\n".join(lines) or content


def missing_inputs_message(call: PlannedCall, question: str) -> str:
    """Ask for what is missing instead of guessing it."""
    lines = []
    for name in call.missing:
        hint = (call.descriptions.get(name) or "").split(".")[0].strip()
        label = name.replace("_", " ")
        lines.append(f"- {label}" + (f": {hint}" if hint else ""))
    if detect_language(question) == "id":
        head = "Untuk menjalankan penilaian ini saya masih membutuhkan:"
        tail = "Sebutkan nilainya di dalam pertanyaan, lalu coba lagi."
    else:
        head = "To run this assessment I still need:"
        tail = "Please include them in your question and ask again."
    return "\n".join([head, *lines, "", tail])
