"""A drafted knowledge object: enrich's output, validate's input.

Mirrors content-service's PublishTermRequest wire shape deliberately
rather than importing content_service.domain.term — services don't share
domain code (the same isolation the import-linter contracts enforce
inside each service), so this is pipeline-service's own copy of what it
needs to produce.
"""

from __future__ import annotations

from pydantic import BaseModel
from pydantic import Field


class EnrichedTerm(BaseModel):
    """A candidate after enrich has drafted its knowledge object.

    aliases/related/prerequisites default empty — nothing in this
    source's grounding (repo grep context) supports inventing them yet.
    """

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$", max_length=64)
    term: str = Field(min_length=1, max_length=64)
    expansion: str = Field(min_length=1, max_length=256)
    definitions: tuple[str, ...] = Field(min_length=1)
    aliases: tuple[str, ...] = ()
    categories: tuple[str, ...] = Field(min_length=1)
    difficulty: int = Field(ge=1, le=5)
    examples: tuple[str, ...] = ()
    related: tuple[str, ...] = ()
    prerequisites: tuple[str, ...] = ()
    common_mistakes: tuple[str, ...] = ()
