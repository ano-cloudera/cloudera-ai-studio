from __future__ import annotations


def classify_connection_error(exc: Exception) -> tuple[str, str]:
    """Return (error_code, safe_message)."""
    name = type(exc).__name__.lower()
    msg = str(exc).casefold()
    if "password" in msg or "authentication" in msg or "auth" in msg and "fail" in msg:
        return "AUTHENTICATION_FAILED", "Authentication failed"
    if "kerberos" in msg or "gssapi" in msg:
        return "KERBEROS_ERROR", "Kerberos authentication failed"
    if "ssl" in msg or "tls" in msg or "certificate" in msg:
        return "TLS_ERROR", "TLS/SSL connection error"
    if "timeout" in msg or "timed out" in name:
        return "TIMEOUT", "Connection timed out"
    if "refused" in msg or "unreachable" in msg or "could not connect" in msg:
        return "HOST_UNREACHABLE", "Host unreachable or connection refused"
    if "database" in msg and ("does not exist" in msg or "not found" in msg):
        return "DATABASE_NOT_FOUND", "Database not found"
    if "catalog" in msg and "not found" in msg:
        return "CATALOG_NOT_FOUND", "Catalog not found"
    if "schema" in msg and "not found" in msg:
        return "SCHEMA_NOT_FOUND", "Schema not found"
    if "permission" in msg or "denied" in msg or "authorized" in msg:
        return "AUTHENTICATION_FAILED", "Authorization denied"
    if "impala" in name or "trino" in name or "psycopg" in name or "dbapi" in name:
        return "DRIVER_ERROR", "Database driver error"
    return "UNKNOWN", "Connection failed"
