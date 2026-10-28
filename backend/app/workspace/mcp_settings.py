"""Workspace MCP server connections (Settings UI)."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MCP_SETTINGS_KEY = "mcp"
McpTransport = Literal["stdio", "sse"]


class McpServerEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    enabled: bool = True
    transport: McpTransport = "stdio"
    command: str | None = Field(default=None, max_length=512)
    args: list[str] = Field(default_factory=list, max_length=32)
    env_var_names: list[str] = Field(
        default_factory=list,
        max_length=16,
        description="Backend process env keys to forward (e.g. BRAVE_API_KEY). Never store secret values here.",
    )
    url: str | None = Field(default=None, max_length=2048)
    header_env_var_names: dict[str, str] = Field(
        default_factory=dict,
        description="SSE header name -> env var name on backend for value lookup.",
    )
    default_tool: str | None = Field(default=None, max_length=120)

    @field_validator("args")
    @classmethod
    def normalize_args(cls, value: list[str]) -> list[str]:
        return [str(a).strip() for a in value if str(a).strip()][:32]

    @field_validator("env_var_names")
    @classmethod
    def normalize_env_keys(cls, value: list[str]) -> list[str]:
        out: list[str] = []
        for raw in value:
            key = str(raw).strip()
            if key and key not in out:
                out.append(key[:128])
        return out[:16]

    @model_validator(mode="after")
    def validate_transport(self) -> McpServerEntry:
        if self.transport == "stdio":
            if not (self.command or "").strip():
                raise ValueError("stdio transport requires command")
        if self.transport == "sse":
            if not (self.url or "").strip():
                raise ValueError("sse transport requires url")
        return self


class McpWorkspaceSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    servers: list[McpServerEntry] = Field(default_factory=list, max_length=20)


def read_mcp_settings(settings_json: dict | None) -> McpWorkspaceSettings:
    block = (settings_json or {}).get(MCP_SETTINGS_KEY) or {}
    if not isinstance(block, dict):
        block = {}
    return McpWorkspaceSettings.model_validate(block)


def write_mcp_settings(settings_json: dict | None, settings: McpWorkspaceSettings) -> dict:
    merged = dict(settings_json or {})
    merged[MCP_SETTINGS_KEY] = settings.model_dump()
    return merged


def enabled_servers(settings_json: dict | None) -> list[McpServerEntry]:
    return [s for s in read_mcp_settings(settings_json).servers if s.enabled]


def server_by_id(settings_json: dict | None, server_id: str) -> McpServerEntry | None:
    needle = (server_id or "").strip()
    if not needle:
        return None
    for row in read_mcp_settings(settings_json).servers:
        if row.id == needle and row.enabled:
            return row
    return None
