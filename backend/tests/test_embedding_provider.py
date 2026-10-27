from __future__ import annotations

from app.core.config import Settings
from app.embeddings.provider import MockEmbeddingProvider, get_embedding_provider


def test_mock_embedding_batch():
    provider = MockEmbeddingProvider(dimension=32)
    vectors = provider.embed_texts(["hello", "world"], batch_size=8)
    assert len(vectors) == 2
    assert len(vectors[0]) == 32


def test_get_mock_from_settings():
    settings = Settings(_env_file=None, embedding_provider="mock")
    provider = get_embedding_provider(settings)
    assert provider.model_name
