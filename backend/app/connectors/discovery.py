from __future__ import annotations

import logging
import uuid
from time import perf_counter
from typing import Any

from app.connectors.base import DatasourceConnector
from app.connectors.errors import ConnectorError, UnsupportedOperationError
from app.connectors.metadata import CatalogInfo, ColumnInfo, SamplePreview, SchemaInfo, TableDetail, TableInfo
from app.connectors.metadata_cache import MetadataCache
from app.connectors.serialization import json_safe_row
from app.connectors.service import ConnectorRegistryService
from app.connectors.sql_compose import preview_select_sql
from app.connectors.type_normalization import normalize_data_type, normalize_table_type
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 100
_MAX_LIMIT = 500


class MetadataDiscoveryService:
    _caches: dict[str, MetadataCache] = {}

    def __init__(
        self,
        registry: ConnectorRegistryService,
        settings: Settings | None = None,
    ) -> None:
        self._registry = registry
        self._settings = settings or get_settings()
        ttl = self._settings.connector_metadata_cache_ttl_seconds
        key = str(ttl)
        if key not in self._caches:
            self._caches[key] = MetadataCache(ttl_seconds=ttl)
        self._cache = self._caches[key]

    def _adapter(self, connector_id: uuid.UUID, *, workspace_id: uuid.UUID, project_id: uuid.UUID) -> DatasourceConnector:
        row = self._registry.get_connector(connector_id, workspace_id=workspace_id, project_id=project_id)
        return self._registry.build_adapter(row)

    def _row(self, connector_id: uuid.UUID, *, workspace_id: uuid.UUID, project_id: uuid.UUID):
        return self._registry.get_connector(connector_id, workspace_id=workspace_id, project_id=project_id)

    def _cache_key(self, connector_id: uuid.UUID, op: str, **parts: Any) -> str:
        frag = ":".join(f"{k}={v}" for k, v in sorted(parts.items()) if v is not None)
        return f"{connector_id}:{op}:{frag}"

    def _paginate(self, items: list, *, limit: int | None, offset: int | None) -> tuple[list, int]:
        limit = min(max(limit or _DEFAULT_LIMIT, 1), _MAX_LIMIT)
        offset = max(offset or 0, 0)
        total = len(items)
        return items[offset : offset + limit], total

    def _filter_tables(
        self,
        tables: list[TableInfo],
        *,
        table_type: str | None,
        search: str | None,
    ) -> list[TableInfo]:
        out = tables
        if table_type:
            want = normalize_table_type(table_type)
            out = [t for t in out if t.table_type == want]
        if search:
            needle = search.casefold()
            out = [t for t in out if needle in t.name.casefold()]
        return out

    def list_catalogs(
        self,
        connector_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        refresh: bool = False,
    ) -> dict:
        started = perf_counter()
        cache_key = self._cache_key(connector_id, "catalogs")
        if not refresh:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached
        adapter = self._adapter(connector_id, workspace_id=workspace_id, project_id=project_id)
        caps = adapter.get_capabilities()
        if not caps.supports_catalogs:
            result = {"catalogs": [], "resolved_context": self._resolved_context(adapter)}
            self._cache.set(cache_key, result)
            return result
        try:
            catalogs = adapter.list_catalogs()
        except UnsupportedOperationError:
            catalogs = []
        payload = {
            "catalogs": [{"name": c.name, "comment": c.comment} for c in catalogs],
            "resolved_context": self._resolved_context(adapter),
        }
        self._cache.set(cache_key, payload)
        logger.info(
            "metadata_catalogs connector_id=%s duration_ms=%.2f count=%s",
            connector_id,
            (perf_counter() - started) * 1000,
            len(catalogs),
        )
        return payload

    def list_schemas(
        self,
        connector_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        catalog: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
        refresh: bool = False,
    ) -> dict:
        started = perf_counter()
        cache_key = self._cache_key(connector_id, "schemas", catalog=catalog, limit=limit, offset=offset)
        if not refresh:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached
        adapter = self._adapter(connector_id, workspace_id=workspace_id, project_id=project_id)
        schemas = adapter.list_schemas(catalog=catalog)
        page, total = self._paginate(schemas, limit=limit, offset=offset)
        payload = {
            "schemas": [{"name": s.name, "catalog": s.catalog, "comment": s.comment} for s in page],
            "total": total,
            "limit": min(max(limit or _DEFAULT_LIMIT, 1), _MAX_LIMIT),
            "offset": max(offset or 0, 0),
            "resolved_context": self._resolved_context(adapter, catalog=catalog),
        }
        self._cache.set(cache_key, payload)
        logger.info(
            "metadata_schemas connector_id=%s catalog=%s duration_ms=%.2f",
            connector_id,
            catalog,
            (perf_counter() - started) * 1000,
        )
        return payload

    def list_tables(
        self,
        connector_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        catalog: str | None = None,
        schema: str | None = None,
        table_type: str | None = None,
        search: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
        refresh: bool = False,
    ) -> dict:
        started = perf_counter()
        cache_key = self._cache_key(
            connector_id,
            "tables",
            catalog=catalog,
            schema=schema,
            table_type=table_type,
            search=search,
        )
        if not refresh:
            cached = self._cache.get(cache_key)
            if cached is not None:
                page, total = self._paginate(cached, limit=limit, offset=offset)
                return {
                    "tables": page,
                    "total": total,
                    "limit": min(max(limit or _DEFAULT_LIMIT, 1), _MAX_LIMIT),
                    "offset": max(offset or 0, 0),
                    "resolved_context": self._resolved_context(self._adapter(connector_id, workspace_id=workspace_id, project_id=project_id), catalog=catalog, schema=schema),
                }
        adapter = self._adapter(connector_id, workspace_id=workspace_id, project_id=project_id)
        tables = adapter.list_tables(catalog=catalog, schema=schema)
        filtered = self._filter_tables(tables, table_type=table_type, search=search)
        serialized = [
            {
                "name": t.name,
                "schema": t.schema,
                "catalog": t.catalog,
                "table_type": t.table_type,
                "comment": t.comment,
            }
            for t in filtered
        ]
        if refresh or not self._cache.get(cache_key):
            self._cache.set(cache_key, serialized)
        page, total = self._paginate(serialized, limit=limit, offset=offset)
        logger.info(
            "metadata_tables connector_id=%s schema=%s duration_ms=%.2f count=%s",
            connector_id,
            schema,
            (perf_counter() - started) * 1000,
            total,
        )
        return {
            "tables": page,
            "total": total,
            "limit": min(max(limit or _DEFAULT_LIMIT, 1), _MAX_LIMIT),
            "offset": max(offset or 0, 0),
            "resolved_context": self._resolved_context(adapter, catalog=catalog, schema=schema),
        }

    def describe_table(
        self,
        connector_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        catalog: str | None,
        schema: str | None,
        table: str,
    ) -> TableDetail:
        from app.connectors.identifiers import validate_identifier

        started = perf_counter()
        validate_identifier(table, label="table")
        adapter = self._adapter(connector_id, workspace_id=workspace_id, project_id=project_id)
        detail = adapter.describe_table_detail(catalog=catalog, schema=schema, table=table)
        from app.connectors.postgres_connector import PostgresConnector

        if isinstance(adapter, PostgresConnector):
            detail = adapter.enrich_table_detail(detail, catalog=catalog, schema=schema, table=table)
        logger.info(
            "metadata_describe connector_id=%s table=%s duration_ms=%.2f",
            connector_id,
            table,
            (perf_counter() - started) * 1000,
        )
        return detail

    def preview_sample(
        self,
        connector_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        catalog: str | None,
        schema: str | None,
        table: str,
        limit: int = 10,
    ) -> SamplePreview:
        from app.connectors.identifiers import validate_identifier

        started = perf_counter()
        validate_identifier(table, label="table")
        row = self._row(connector_id, workspace_id=workspace_id, project_id=project_id)
        adapter = self._registry.build_adapter(row)
        limit = min(max(limit, 1), 100)
        default_cat, default_schema = adapter.default_context()
        resolved_catalog = catalog or default_cat
        resolved_schema = schema or default_schema
        sql = preview_select_sql(
            connector_type=row.connector_type,
            catalog=resolved_catalog,
            schema=resolved_schema,
            table=table,
            limit=limit,
        )
        result = adapter.execute_readonly_query(sql, max_rows=limit)
        safe_rows = [json_safe_row(r) for r in result.rows[:limit]]
        duration = round((perf_counter() - started) * 1000, 3)
        logger.info(
            "metadata_preview connector_id=%s table=%s rows=%s duration_ms=%s",
            connector_id,
            table,
            len(safe_rows),
            duration,
        )
        return SamplePreview(
            columns=result.columns,
            rows=safe_rows,
            row_count=len(safe_rows),
            truncated=len(safe_rows) >= limit,
            query_duration_ms=duration,
            resolved_catalog=resolved_catalog,
            resolved_schema=resolved_schema,
            resolved_table=table,
        )

    def source_summary(
        self,
        connector_id: uuid.UUID,
        *,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> dict:
        row = self._row(connector_id, workspace_id=workspace_id, project_id=project_id)
        adapter = self._adapter(connector_id, workspace_id=workspace_id, project_id=project_id)
        caps = adapter.get_capabilities()
        catalogs_count = 0
        schemas_count = 0
        tables_count = 0
        views_count = 0
        if caps.supports_catalogs:
            catalogs_count = len(adapter.list_catalogs())
        schemas = adapter.list_schemas(catalog=None)
        schemas_count = len(schemas)
        for sch in schemas[:20]:
            tables = adapter.list_tables(catalog=sch.catalog, schema=sch.name)
            for t in tables:
                if t.table_type == "VIEW":
                    views_count += 1
                else:
                    tables_count += 1
        return {
            "connector_id": str(connector_id),
            "connector_name": row.name,
            "connector_type": row.connector_type,
            "catalogs": catalogs_count,
            "schemas": schemas_count,
            "tables": tables_count,
            "views": views_count,
            "bounded": True,
            "note": "Counts are bounded (first 20 schemas); not a full cluster scan.",
        }

    def capabilities(self, connector_id: uuid.UUID, *, workspace_id: uuid.UUID, project_id: uuid.UUID) -> dict:
        adapter = self._adapter(connector_id, workspace_id=workspace_id, project_id=project_id)
        return adapter.get_capabilities().to_api_dict()

    @staticmethod
    def table_detail_dict(detail: TableDetail) -> dict:
        return {
            "catalog": detail.catalog,
            "schema": detail.schema,
            "name": detail.name,
            "table_type": detail.table_type,
            "comment": detail.comment,
            "primary_key": detail.primary_key,
            "metadata": detail.metadata,
            "columns": [
                {
                    "name": c.name,
                    "data_type": c.data_type,
                    "native_type": c.native_type or c.data_type,
                    "normalized_type": c.normalized_type,
                    "nullable": c.nullable,
                    "ordinal_position": c.ordinal_position,
                    "comment": c.comment,
                }
                for c in detail.columns
            ],
        }

    @staticmethod
    def sample_dict(sample: SamplePreview) -> dict:
        return {
            "columns": sample.columns,
            "rows": sample.rows,
            "row_count": sample.row_count,
            "truncated": sample.truncated,
            "query_duration_ms": sample.query_duration_ms,
            "resolved_context": {
                "catalog": sample.resolved_catalog,
                "schema": sample.resolved_schema,
                "table": sample.resolved_table,
            },
        }

    def _resolved_context(
        self,
        adapter: DatasourceConnector,
        *,
        catalog: str | None = None,
        schema: str | None = None,
    ) -> dict:
        default_cat, default_schema = adapter.default_context()
        return {
            "catalog": catalog or default_cat,
            "schema": schema or default_schema,
            "default_catalog": default_cat,
            "default_schema": default_schema,
        }
