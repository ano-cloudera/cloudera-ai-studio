from __future__ import annotations

import pytest

from app.storage.object_store import NFSObjectStore, ObjectStoreError


def test_put_get_delete_roundtrip(tmp_path):
    store = NFSObjectStore(tmp_path)
    key = "ws/proj/lib/doc/original/file.txt"
    store.put(key, b"hello")
    assert store.exists(key)
    assert store.get(key) == b"hello"
    store.delete(key)
    assert not store.exists(key)


def test_rejects_path_traversal(tmp_path):
    store = NFSObjectStore(tmp_path)
    with pytest.raises(ObjectStoreError):
        store.put("../../etc/passwd", b"x")
