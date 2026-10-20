"""Tests for embedding cache and strict fallback behavior.

These are unit tests: no network, no Qdrant. The provider call is monkeypatched.
"""

from __future__ import annotations

import pytest

from compliance.rag import embeddings


@pytest.fixture(autouse=True)
def _clear_cache():
    embeddings.clear_embedding_cache()
    yield
    embeddings.clear_embedding_cache()


def test_cache_hit_avoids_second_provider_call(monkeypatch):
    calls = []

    def fake_post(texts, model):
        calls.append(list(texts))
        return [[float(len(t))] * 2048 for t in texts]

    monkeypatch.setattr(embeddings, "_post_embeddings_batch", fake_post)

    first = embeddings.embed_texts(["alpha", "beta"])
    second = embeddings.embed_texts(["alpha", "beta"])

    assert first == second
    assert len(calls) == 1, "second call should be served entirely from cache"


def test_cache_only_embeds_misses(monkeypatch):
    calls = []

    def fake_post(texts, model):
        calls.append(list(texts))
        return [[1.0] * 2048 for _ in texts]

    monkeypatch.setattr(embeddings, "_post_embeddings_batch", fake_post)

    embeddings.embed_texts(["alpha"])
    embeddings.embed_texts(["alpha", "gamma"])

    assert calls[0] == ["alpha"]
    assert calls[1] == ["gamma"], "cached 'alpha' must not be re-embedded"


def test_cache_preserves_order(monkeypatch):
    def fake_post(texts, model):
        # Encode the text in the first component so order is checkable.
        return [[float(ord(t[0]))] * 2048 for t in texts]

    monkeypatch.setattr(embeddings, "_post_embeddings_batch", fake_post)

    vectors = embeddings.embed_texts(["a", "b", "c"])
    assert [v[0] for v in vectors] == [float(ord("a")), float(ord("b")), float(ord("c"))]


def test_failure_raises_instead_of_silent_fallback(monkeypatch):
    def failing_post(texts, model):
        raise embeddings.EmbeddingError("upstream 504")

    monkeypatch.setattr(embeddings, "_post_embeddings_batch", failing_post)
    monkeypatch.setattr(embeddings, "MAX_RETRIES", 1)

    with pytest.raises(embeddings.EmbeddingError, match="Refusing to silently switch"):
        embeddings.embed_texts(["alpha"])


def test_explicit_fallback_uses_local_model(monkeypatch):
    def failing_post(texts, model):
        raise embeddings.EmbeddingError("upstream 504")

    monkeypatch.setattr(embeddings, "_post_embeddings_batch", failing_post)
    monkeypatch.setattr(embeddings, "MAX_RETRIES", 1)
    monkeypatch.setattr(embeddings, "_local_embed", lambda texts, model: [[0.1] * 384 for _ in texts])

    vectors = embeddings.embed_texts(["alpha"], allow_fallback=True)
    assert len(vectors[0]) == 384


def test_empty_input_returns_empty():
    assert embeddings.embed_texts([]) == []


def test_unknown_model_dimension_raises():
    with pytest.raises(embeddings.EmbeddingError):
        embeddings.embedding_dim(model="not-a-real-model", provider="openrouter")
