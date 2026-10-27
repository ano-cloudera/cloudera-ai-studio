from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator

from app.core.models import StrictModel
from app.connectors.errors import ConnectorError

ConnectorType = Literal["impala", "trino", "postgres"]
AuthType = Literal["plain", "ldap", "gssapi", "none"]


class ImpalaConnectorConfig(StrictModel):
    host: str = Field(min_length=1)
    port: int = Field(default=21050, ge=1, le=65535)
    database: str = Field(default="default")
    auth_type: AuthType = "plain"
    username: str | None = None
    kerberos_service_name: str | None = "impala"
    ssl: bool = False
    http_transport: bool = False
    http_path: str = ""
    timeout_seconds: int | None = None


class TrinoConnectorConfig(StrictModel):
    host: str = Field(min_length=1)
    port: int = Field(default=8080, ge=1, le=65535)
    catalog: str = Field(default="")
    schema: str | None = None
    http_scheme: Literal["http", "https"] = "http"
    auth_type: AuthType = "none"
    username: str | None = "trino"
    verify_ssl: bool = True
    timeout_seconds: int | None = None


class PostgresConnectorConfig(StrictModel):
    host: str = Field(min_length=1)
    port: int = Field(default=5432, ge=1, le=65535)
    database: str = Field(min_length=1)
    username: str | None = None
    sslmode: Literal["disable", "prefer", "require", "verify-ca", "verify-full"] = "prefer"
    timeout_seconds: int | None = None


def parse_connector_config(connector_type: str, raw: dict[str, Any]) -> ImpalaConnectorConfig | TrinoConnectorConfig | PostgresConnectorConfig:
    try:
        if connector_type == "impala":
            return ImpalaConnectorConfig.model_validate(raw or {})
        if connector_type == "trino":
            return TrinoConnectorConfig.model_validate(raw or {})
        if connector_type == "postgres":
            return PostgresConnectorConfig.model_validate(raw or {})
    except Exception as exc:
        raise ConnectorError("INVALID_CONFIG", str(exc), 422) from exc
    raise ConnectorError("INVALID_CONFIG", f"Unknown connector type: {connector_type}", 422)
