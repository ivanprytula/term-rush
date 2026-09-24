"""A candidate term: an extraction result, not yet a Term.

Carries provenance and confidence per source (ADR-0004) so later pipeline
stages (enrich, validate, review) can decide what to do with it without
re-deriving where it came from.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class SourceType(StrEnum):
    """Where a candidate was extracted from. Drives default confidence."""

    DEPENDENCY_MANIFEST = "dependency_manifest"


class Confidence(StrEnum):
    """How much a source's candidates can be trusted without review."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TermCandidate(BaseModel):
    """One extracted name, not yet a knowledge object.

    `name` is the raw extracted token (e.g. a package name); it becomes
    `Term.term`/`Term.expansion` only after the enrich stage drafts a
    knowledge object around it — extraction does not invent definitions.
    """

    model_config = {"frozen": True}

    name: str
    source_type: SourceType
    source_file: str
    confidence: Confidence
