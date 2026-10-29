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


def test_delete_prunes_empty_parent_folders_but_keeps_siblings_and_root(tmp_path):
    store = NFSObjectStore(tmp_path)
    store.put("ws/proj/lib/doc1/original/a.pdf", b"a")
    store.put("ws/proj/lib/doc2/original/b.pdf", b"b")
    store.delete("ws/proj/lib/doc1/original/a.pdf")
    assert not (tmp_path / "ws/proj/lib/doc1").exists()
    assert store.exists("ws/proj/lib/doc2/original/b.pdf")
    store.delete("ws/proj/lib/doc2/original/b.pdf")
    assert not (tmp_path / "ws").exists()
    assert tmp_path.exists()


def test_rejects_path_traversal(tmp_path):
    store = NFSObjectStore(tmp_path)
    with pytest.raises(ObjectStoreError):
        store.put("../../etc/passwd", b"x")
