"""ONNX-runtime adapter for EmbeddingPort (ADR-0012 Slice 2).

fastembed, not sentence-transformers/torch: same all-MiniLM-L6-v2 model,
running through ONNX Runtime instead of a full torch stack — no CUDA
kernels, no ~1GB dependency tree, for CPU-only inference this project
never needed the GPU path for anyway.

TextEmbedding.embed() is synchronous, CPU-bound work — calling it directly
from an async method would block the event loop the same way any other
unyielded CPU-bound call would. Offloaded to a thread via
`asyncio.to_thread` so it doesn't stall concurrent requests, the same
reasoning the async-python skills-map entry tracks generally.
"""

from __future__ import annotations

import asyncio

from fastembed import TextEmbedding

from content_service.domain.constants import DOCUMENT_CHUNK_EMBEDDING_DIM

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


class OnnxEmbedder:
    """Embeds text with a local ONNX all-MiniLM-L6-v2 model.

    Loads the model once at construction (downloads/caches on first run,
    then a few hundred ms to initialize) and reuses it for every call —
    re-loading per request would dominate the actual embedding time.
    """

    def __init__(self, model_name: str = MODEL_NAME) -> None:
        # Checked before construction (get_embedding_size is a metadata
        # lookup, not an instantiation) so a dimension mismatch fails fast
        # without first paying the model-load cost.
        dim = TextEmbedding.get_embedding_size(model_name)
        if dim != DOCUMENT_CHUNK_EMBEDDING_DIM:
            raise ValueError(
                f"{model_name} outputs {dim}-dim vectors, but "
                f"DOCUMENT_CHUNK_EMBEDDING_DIM is {DOCUMENT_CHUNK_EMBEDDING_DIM} — "
                "the pgvector column is sized for a specific model; changing "
                "models means a migration, not just a constant edit."
            )
        self._model = TextEmbedding(model_name=model_name)

    def _encode_one(self, text: str) -> list[float]:
        # embed() is a generator over the input iterable; one string in,
        # one vector out.
        (vector,) = self._model.embed([text])
        return vector.tolist()

    async def embed(self, text: str) -> list[float]:
        return await asyncio.to_thread(self._encode_one, text)
