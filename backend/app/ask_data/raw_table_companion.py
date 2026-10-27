"""Expand raw table Ask Data context to related tables on the same connector (same schema)."""
from __future__ import annotations

import re
import uuid

from sqlalchemy.orm import Session

from app.ask_data.physical_identifiers import normalize_table_key, qualified_physical_name
from app.ask_data.table_context_id import RawTableRef
from app.connectors.discovery import MetadataDiscoveryService
from app.connectors.service import ConnectorRegistryService
from app.core.config import Settings


def _question_mentions_table(question: str, table_name: str) -> bool:
    name = table_name.casefold()
    text = question.casefold()
    if name in text:
        return True
    return bool(re.search(rf"\b{re.escape(name)}\b", text))


def expand_raw_table_context(
    session: Session,
    *,
    settings: Settings,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    ref: RawTableRef,
    question: str,
    primary_qualified: str,
    primary_columns: list[str],
) -> tuple[frozenset[str], dict]:
    """Return (allowed_physical_tables, raw_table_policy dict)."""
    allowed = {normalize_table_key(primary_qualified)}
    tables_meta = [
        {
            "qualified_name": primary_qualified,
            "columns": [c.casefold() for c in primary_columns if c],
        }
    ]
    registry = ConnectorRegistryService(session, settings=settings)
    discovery = MetadataDiscoveryService(registry, settings=settings)
    try:
        payload = discovery.list_tables(
            ref.connector_id,
            workspace_id=workspace_id,
            project_id=project_id,
            schema=ref.schema,
            limit=200,
        )
    except Exception:
        payload = {"tables": []}
    schema = ref.schema or "public"
    row = registry.get_connector(ref.connector_id, workspace_id=workspace_id, project_id=project_id)
    for item in payload.get("tables") or []:
        name = str(item.get("name") or "").strip()
        if not name or name == ref.table:
            continue
        if not _question_mentions_table(question, name):
            continue
        try:
            qualified = qualified_physical_name(
                connector_type=row.connector_type,
                catalog=ref.catalog,
                schema=schema,
                table_name=name,
                view_name=None,
            )
        except ValueError:
            continue
        allowed.add(normalize_table_key(qualified))
        try:
            detail = discovery.describe_table(
                ref.connector_id,
                workspace_id=workspace_id,
                project_id=project_id,
                catalog=ref.catalog,
                schema=schema,
                table=name,
            )
            cols = [c.name for c in detail.columns if c.name]
        except Exception:
            cols = []
        tables_meta.append({"qualified_name": qualified, "columns": [c.casefold() for c in cols]})

    policy = {
        "qualified_name": primary_qualified,
        "columns": [c.casefold() for c in primary_columns if c],
        "tables": tables_meta,
    }
    return frozenset(allowed), policy
