"""OnnxEmbedder against the real model (ADR-0012 Slice 2).

No mocking the model itself — the point of this test is proving the actual
adapter contract (dimension, determinism, async-safety) holds against real
ONNX output, not just against a fake. Downloads/caches a small (~90MB)
model on first run.
"""

from __future__ import annotations

import pytest

from content_service.domain import constants
from content_service.infrastructure.onnx_embedder import OnnxEmbedder


@pytest.fixture(scope="module")
def embedder() -> OnnxEmbedder:
    return OnnxEmbedder()


@pytest.mark.asyncio
async def test_embed_returns_the_configured_dimension(embedder: OnnxEmbedder) -> None:
    vector = await embedder.embed("gradient descent")

    assert len(vector) == constants.DOCUMENT_CHUNK_EMBEDDING_DIM


@pytest.mark.asyncio
async def test_embed_is_deterministic(embedder: OnnxEmbedder) -> None:
    first = await embedder.embed("gradient descent")
    second = await embedder.embed("gradient descent")

    assert first == second


@pytest.mark.asyncio
async def test_embed_differs_for_different_text(embedder: OnnxEmbedder) -> None:
    a = await embedder.embed("gradient descent")
    b = await embedder.embed("chocolate chip cookies")

    assert a != b


def test_construction_rejects_a_model_with_mismatched_dimension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # get_embedding_size is a metadata lookup, so this never loads a real
    # model (mismatched or otherwise) — the guard fires before that cost.
    monkeypatch.setattr(
        "content_service.infrastructure.onnx_embedder.TextEmbedding.get_embedding_size",
        staticmethod(lambda model_name: 768),
    )

    with pytest.raises(ValueError, match="384"):
        OnnxEmbedder(model_name="sentence-transformers/all-MiniLM-L6-v2")
