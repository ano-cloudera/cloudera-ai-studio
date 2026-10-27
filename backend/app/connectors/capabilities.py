from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ConnectorCapabilities:
    supports_sql: bool = True
    supports_metadata_discovery: bool = True
    supports_catalogs: bool = False
    supports_schemas: bool = True
    supports_tables: bool = True
    supports_views: bool = True
    supports_read_only_query: bool = True
    supports_sample_preview: bool = True
    supports_transactions: bool = False
    supports_kerberos: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    def to_api_dict(self) -> dict:
        return {
            "sql": self.supports_sql,
            "metadata": self.supports_metadata_discovery,
            "catalogs": self.supports_catalogs,
            "schemas": self.supports_schemas,
            "tables": self.supports_tables,
            "views": self.supports_views,
            "read_only_query": self.supports_read_only_query,
            "sample_preview": self.supports_sample_preview,
            "transactions": self.supports_transactions,
            "kerberos": self.supports_kerberos,
        }


IMPALA_CAPABILITIES = ConnectorCapabilities(
    supports_catalogs=False,
    supports_kerberos=True,
)

TRINO_CAPABILITIES = ConnectorCapabilities(
    supports_catalogs=True,
)

POSTGRES_CAPABILITIES = ConnectorCapabilities(
    supports_catalogs=False,
)
