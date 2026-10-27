"""Object/document storage abstraction (NFS-backed local path in M2A)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


class ObjectStoreError(Exception):
    pass


@runtime_checkable
class ObjectStore(Protocol):
    def put(self, key: str, data: bytes) -> None: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...

    def exists(self, key: str) -> bool: ...


def _normalize_key(key: str) -> str:
    cleaned = key.replace("\\", "/").strip("/")
    if not cleaned or ".." in cleaned.split("/"):
        raise ObjectStoreError("invalid storage key")
    return cleaned


class NFSObjectStore:
    """Stores blobs under a configured root (NFS mount in production)."""

    def __init__(self, root: Path) -> None:
        self._root = root.expanduser().resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def _path_for(self, key: str) -> Path:
        relative = _normalize_key(key)
        target = (self._root / relative).resolve()
        if not str(target).startswith(str(self._root)):
            raise ObjectStoreError("path traversal rejected")
        return target

    def put(self, key: str, data: bytes) -> None:
        path = self._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        path = self._path_for(key)
        if not path.is_file():
            raise ObjectStoreError("object not found")
        return path.read_bytes()

    def delete(self, key: str) -> None:
        path = self._path_for(key)
        if not path.exists():
            raise ObjectStoreError("object not found")
        if path.is_file():
            path.unlink()
            return
        if path.is_dir():
            for child in sorted(path.rglob("*"), reverse=True):
                if child.is_file():
                    child.unlink()
                elif child.is_dir():
                    child.rmdir()
            path.rmdir()
            return
        raise ObjectStoreError("object not found")

    def exists(self, key: str) -> bool:
        try:
            return self._path_for(key).exists()
        except ObjectStoreError:
            return False


def build_object_store(root: Path) -> ObjectStore:
    return NFSObjectStore(root)
