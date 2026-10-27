from __future__ import annotations

from fastapi import APIRouter

from app.skills.tool_registry import ToolRegistry

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("")
def list_tools() -> dict:
    tools = ToolRegistry.list_tools()
    return {
        "tools": [
            {
                "key": t.key,
                "name": t.name,
                "description": t.description,
                "enabled": t.enabled,
                "input_schema": t.input_schema,
            }
            for t in tools
        ]
    }
