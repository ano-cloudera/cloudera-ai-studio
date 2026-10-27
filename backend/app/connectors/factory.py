from __future__ import annotations

from app.connectors.base import DatasourceConnector
from app.connectors.config import (
    ImpalaConnectorConfig,
    PostgresConnectorConfig,
    TrinoConnectorConfig,
    parse_connector_config,
)
from app.connectors.errors import ConnectorError
from app.connectors.impala_connector import ImpalaConnector
from app.connectors.postgres_connector import PostgresConnector
from app.connectors.secrets import SecretProvider
from app.connectors.trino_connector import TrinoConnector
from app.core.config import Settings, get_settings


class ConnectorFactory:
    def __init__(
        self,
        settings: Settings | None = None,
        secret_provider: SecretProvider | None = None,
    ) -> None:
        from app.connectors.secrets import EnvironmentSecretProvider

        self._settings = settings or get_settings()
        self._secrets = secret_provider or EnvironmentSecretProvider()

    def create(
        self,
        connector_type: str,
        config: dict,
        *,
        secret_ref: str | None = None,
    ) -> DatasourceConnector:
        typed = parse_connector_config(connector_type, config)
        password = self._resolve_password(connector_type, typed, secret_ref)
        connect_timeout = self._settings.connector_connect_timeout_seconds
        query_timeout = self._settings.connector_query_timeout_seconds
        metadata_timeout = self._settings.connector_metadata_timeout_seconds

        if connector_type == "impala":
            assert isinstance(typed, ImpalaConnectorConfig)
            return ImpalaConnector(
                typed,
                password=password,
                connect_timeout_seconds=connect_timeout,
                query_timeout_seconds=query_timeout,
            )
        if connector_type == "trino":
            assert isinstance(typed, TrinoConnectorConfig)
            return TrinoConnector(typed, password=password, query_timeout_seconds=query_timeout)
        if connector_type == "postgres":
            assert isinstance(typed, PostgresConnectorConfig)
            return PostgresConnector(
                typed,
                password=password,
                connect_timeout_seconds=connect_timeout,
                query_timeout_seconds=query_timeout,
                metadata_timeout_seconds=metadata_timeout,
            )
        raise ConnectorError("INVALID_CONFIG", f"Unsupported connector type: {connector_type}", 422)

    def _resolve_password(self, connector_type: str, typed, secret_ref: str | None) -> str | None:
        if not secret_ref:
            if connector_type == "impala" and getattr(typed, "auth_type", None) in {"plain", "ldap"}:
                raise ConnectorError("SECRET_NOT_FOUND", "Password secret required for Impala auth", 422)
            return None
        return self._secrets.get_secret(secret_ref)
