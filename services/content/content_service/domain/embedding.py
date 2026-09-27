"""The embedding port for document chunks (ADR-0012 Slice 2).

Declared here, not in application/ports.py, for the same reason
game-service's LLMJudgePort lives in its domain/: this is a domain-level
collaborator for DocumentChunk, not an application-owned repository
contract. Application composes it; it does not own the contract.
"""

from __future__ import annotations

from typing import Protocol


class EmbeddingPort(Protocol):
    """Turns chunk text into a fixed-length vector for similarity search.

    Implemented by an infrastructure adapter (a local sentence-transformers
    model today; ADR-0012 anticipates swapping to a managed provider, e.g.
    AWS Bedrock, without touching this contract or any caller).
    """

    async def embed(self, text: str) -> list[float]:
        """Embed one chunk of text. Raises on model/provider failure —
        callers decide whether a chunk stays un-embedded and keyword-
        searchable rather than catching provider-specific exceptions here.
        """
        ...
