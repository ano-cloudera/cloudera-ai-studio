from __future__ import annotations

import logging
from time import perf_counter

from app.core.config import Settings, get_settings
from app.db.base import BackendColumn, BackendExecutionContext, BackendQueryResult, DataBackendError, DataBackendHealth, QueryTelemetry, normalize_value


logger = logging.getLogger(__name__)


def is_impala_configured(settings: Settings) -> bool:
    if not settings.impala_host:
        return False
    mechanism = settings.impala_auth_mechanism.upper()
    if mechanism == "GSSAPI":
        return bool(settings.impala_kerberos_service_name)
    if mechanism in {"PLAIN", "LDAP"}:
        return bool(settings.impala_user and settings.impala_password)
    return True


def _is_transient_connection_error(exc: Exception) -> bool:
    """Return true only for failures where opening a fresh connection is safe.

    Impyla can surface gateway and Thrift transport failures through several
    exception classes depending on the selected HTTP/binary transport. Keep
    this deliberately conservative: authentication and SQL analysis failures
    must never be retried as if they were network blips.
    """

    name = type(exc).__name__.lower()
    message = str(exc).lower()
    response = getattr(exc, "response", None)
    if response is None:
        response = getattr(exc, "http_response", None)
    status = getattr(response, "status_code", None)
    if status in (401, 403) or any(
        term in message
        for term in ("authentication", "unauthorized", "forbidden", "analysisexception", "parseexception")
    ):
        return False
    if status in (502, 503, 504):
        return True
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    if any(term in name for term in ("connection", "timeout", "transport")):
        return True
    return any(
        term in message
        for term in (
            "connection reset",
            "connection refused",
            "remote end closed",
            "broken pipe",
            "temporarily unavailable",
            "timed out",
            "timeout",
        )
    )


def _is_authentication_error(exc: Exception) -> bool:
    message = str(exc).casefold()
    code = getattr(exc, "code", None)
    response = getattr(exc, "response", None)
    if response is None:
        response = getattr(exc, "http_response", None)
    status = getattr(response, "status_code", None)
    return code in (401, 403) or status in (401, 403) or any(
        term in message for term in ("401", "403", "unauthorized", "forbidden", "authentication")
    )


class ImpalaBackend:
    dialect = "hive"
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def health(self) -> tuple[str, str]:
        configured = is_impala_configured(self.settings)
        return ("configured" if configured else "degraded", "impala")

    def health_check(self, probe: bool = False) -> DataBackendHealth:
        configured = is_impala_configured(self.settings)
        return DataBackendHealth(type="impala", status="unknown" if configured else "misconfigured")

    def query(self, sql: str) -> list[dict]:
        try:
            from impala.dbapi import connect
        except ImportError as exc:
            raise RuntimeError("Impala dependencies are not installed. Use requirements-impala.txt") from exc

        conn = connect(
            host=self.settings.impala_host,
            port=self.settings.impala_port,
            database=self.settings.impala_database,
            auth_mechanism=self.settings.impala_auth_mechanism,
            user=self.settings.impala_user or None,
            password=self.settings.impala_password or None,
            use_ssl=self.settings.impala_use_ssl,
            use_http_transport=self.settings.impala_use_http_transport,
            http_path=self.settings.impala_http_path,
            kerberos_service_name=self.settings.impala_kerberos_service_name,
        )
        cursor = conn.cursor()
        try:
            cursor.execute(sql, configuration={"QUERY_TIMEOUT_S": str(self.settings.impala_query_timeout_seconds)})
            columns = [item[0] for item in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            cursor.close()
            conn.close()

    def execute(self, sql: str, context: BackendExecutionContext | None = None) -> BackendQueryResult:
        context = context or BackendExecutionContext()
        started = perf_counter()
        for attempt in range(2):
            try:
                records = self.query(sql)
                break
            except Exception as exc:
                retrying = attempt == 0 and _is_transient_connection_error(exc)
                safe_error_code = "IMPALA_AUTH_FAILED" if _is_authentication_error(exc) else "IMPALA_QUERY_FAILED"
                logger.warning(
                    "data_query backend=impala success=false driver_error_type=%s safe_error_code=%s "
                    "attempt=%d retrying=%s trace_id=%s",
                    type(exc).__name__,
                    safe_error_code,
                    attempt + 1,
                    str(retrying).lower(),
                    context.trace_id,
                )
                if retrying:
                    continue
                telemetry = QueryTelemetry(
                    data_backend="impala",
                    query_latency_ms=(perf_counter() - started) * 1000,
                    row_count=0,
                    success=False,
                    safe_error_code=safe_error_code,
                )
                raise DataBackendError(safe_error_code, telemetry) from exc
        names = list(records[0]) if records else []
        rows = [[normalize_value(record.get(name)) for name in names] for record in records]
        return BackendQueryResult(
            columns=[BackendColumn(name=name, type="unknown") for name in names],
            rows=rows,
            row_count=len(rows),
            telemetry=QueryTelemetry(
                data_backend="impala",
                query_latency_ms=(perf_counter() - started) * 1000,
                row_count=len(rows),
                success=True,
            ),
        )

    def close(self) -> None:
        return None
