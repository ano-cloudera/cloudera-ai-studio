import pytest

from app.core.config import Settings
from app.db.base import DataBackendError
from app.db.impala_backend import ImpalaBackend, is_impala_configured


def test_ldap_profile_requires_both_user_and_password() -> None:
    settings = Settings(
        impala_host="impala.example",
        impala_auth_mechanism="LDAP",
        impala_user="tempo-user",
        impala_password="",
    )

    assert is_impala_configured(settings) is False


def test_http_401_is_reported_as_auth_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = ImpalaBackend(Settings(impala_host="impala.example"))
    unauthorized = RuntimeError("HTTP code 401: Unauthorized")
    monkeypatch.setattr(backend, "query", lambda _sql: (_ for _ in ()).throw(unauthorized))

    with pytest.raises(DataBackendError) as captured:
        backend.execute("SELECT 1")

    assert captured.value.code == "IMPALA_AUTH_FAILED"
    assert captured.value.telemetry is not None
    assert captured.value.telemetry.safe_error_code == "IMPALA_AUTH_FAILED"


@pytest.mark.parametrize("status_code", [401, 403])
def test_falsy_http_response_is_reported_as_auth_failure(
    monkeypatch: pytest.MonkeyPatch, status_code: int
) -> None:
    class FalsyResponse:
        def __init__(self, status: int) -> None:
            self.status_code = status

        def __bool__(self) -> bool:
            return False

    class HttpFailure(RuntimeError):
        def __init__(self, status: int) -> None:
            super().__init__("session rejected")
            self.response = FalsyResponse(status)

    backend = ImpalaBackend(Settings(impala_host="impala.example"))
    monkeypatch.setattr(
        backend, "query", lambda _sql: (_ for _ in ()).throw(HttpFailure(status_code))
    )

    with pytest.raises(DataBackendError) as captured:
        backend.execute("SELECT 1")

    assert captured.value.code == "IMPALA_AUTH_FAILED"
