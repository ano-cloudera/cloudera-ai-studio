from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from app.core.config import BACKEND_ROOT, Settings, get_settings
from app.semantic_registry.governance_types import VALIDATOR_VERSION
from app.semantic_registry.runtime_adapter import OssieRuntimeAdapter

GENERATOR_VERSION = "s4.0"


def deployment_dir(
    settings: Settings,
    *,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    model_key: str,
    deployment_id: uuid.UUID,
) -> Path:
    root = Path(settings.semantic_runtime_storage_root)
    if not root.is_absolute():
        root = (BACKEND_ROOT / root).resolve()
    return root / str(workspace_id) / str(project_id) / model_key / "deployments" / str(deployment_id)


def logical_artifact_uri(model_key: str, deployment_id: uuid.UUID) -> str:
    return f"semantic-runtime://{model_key}/deployments/{deployment_id}"


def write_deployment_artifact(
    session,
    *,
    settings: Settings | None,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    model_key: str,
    deployment_id: uuid.UUID,
    version_id: uuid.UUID,
    version_number: int,
    source_validation_run_id: uuid.UUID | None,
) -> tuple[str, str, dict, Path]:
    settings = settings or get_settings()
    dest_root = deployment_dir(
        settings,
        workspace_id=workspace_id,
        project_id=project_id,
        model_key=model_key,
        deployment_id=deployment_id,
    )
    ossie_dir = dest_root / "ossie"
    ossie_dir.mkdir(parents=True, exist_ok=True)

    from app.db.platform_models import SemanticModelRow, SemanticVersionRow
    from app.semantic_runtime.publish_governance import build_publish_governance

    artifact = OssieRuntimeAdapter().generate_artifact(session, version_id, write_file=False)
    core_path = ossie_dir / "tempo_core.ossie.yaml"
    core_path.write_text(artifact.content, encoding="utf-8")
    checksum = hashlib.sha256(core_path.read_bytes()).hexdigest()

    version_row = session.get(SemanticVersionRow, version_id)
    model_row = (
        session.get(SemanticModelRow, version_row.semantic_model_id) if version_row else None
    )
    parsed_core = yaml.safe_load(artifact.content) or {}
    datasets = {d["name"]: d for d in (parsed_core.get("datasets") or []) if isinstance(d, dict) and d.get("name")}
    governance_doc = (
        build_publish_governance(
            session,
            version_id=version_id,
            model=model_row,
            datasets=datasets,
        )
        if model_row
        else {
            "ambiguities": [],
            "unknown_metric_question": "Which metric would you like to report on?",
            "scope": {},
        }
    )
    (ossie_dir / "tempo_governance.yaml").write_text(
        yaml.safe_dump(governance_doc, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    from app.semantic_runtime.certified_questions import build_certified_golden_questions

    golden = build_certified_golden_questions(
        session,
        workspace_id=workspace_id,
        model=model_row,
    )
    (ossie_dir / "golden_questions.yaml").write_text(
        yaml.safe_dump({"questions": golden}, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    manifest = {
        "deployment_id": str(deployment_id),
        "semantic_version_id": str(version_id),
        "registry_version": version_number,
        "artifact_checksum": checksum,
        "runtime_adapter": artifact.adapter,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_validation_run_id": str(source_validation_run_id) if source_validation_run_id else None,
        "generator_version": GENERATOR_VERSION,
        "object_counts": artifact.metadata,
    }
    (dest_root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    uri = logical_artifact_uri(model_key, deployment_id)
    return uri, checksum, manifest, dest_root
