from __future__ import annotations


class ConnectorError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class UnsupportedOperationError(ConnectorError):
    def __init__(self, message: str = "Operation not supported by this connector") -> None:
        super().__init__("UNSUPPORTED_OPERATION", message, 400)
