from __future__ import annotations

from pathlib import Path

PROFILE_MARKERS = {
    "aws": "### IMPALA CREDENTIALS AWS ENV",
    "ingram": "### IMPALA CREDENTIALS INGRAM ENV",
}

IMPALA_KEYS = {
    "IMPALA_HOST": "impala_host",
    "IMPALA_PORT": "impala_port",
    "IMPALA_DATABASE": "impala_database",
    "IMPALA_AUTH_MECHANISM": "impala_auth_mechanism",
    "IMPALA_USER": "impala_user",
    "IMPALA_PASSWORD": "impala_password",
    "IMPALA_USE_SSL": "impala_use_ssl",
    "IMPALA_USE_HTTP_TRANSPORT": "impala_use_http_transport",
    "IMPALA_HTTP_PATH": "impala_http_path",
    "IMPALA_KERBEROS_SERVICE_NAME": "impala_kerberos_service_name",
    "IMPALA_QUERY_TIMEOUT_SECONDS": "impala_query_timeout_seconds",
}


def load_impala_profile(env_path: Path, profile: str) -> dict[str, object]:
    marker = PROFILE_MARKERS.get(profile.strip().lower())
    if not marker or not env_path.is_file():
        return {}

    active = False
    raw: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("###"):
            active = stripped == marker
            continue
        if not active or not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key.startswith("IMPALA_"):
            raw[key] = value.strip().strip('"').strip("'")

    parsed: dict[str, object] = {}
    for env_key, field_name in IMPALA_KEYS.items():
        if env_key not in raw:
            continue
        value = raw[env_key]
        if field_name in {"impala_port", "impala_query_timeout_seconds"}:
            parsed[field_name] = int(value)
        elif field_name in {"impala_use_ssl", "impala_use_http_transport"}:
            parsed[field_name] = value.lower() in {"1", "true", "yes", "on"}
        else:
            parsed[field_name] = value
    return parsed
