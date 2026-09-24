"""Load the hand-authored curated source (ADR-0004): parse
curated_terms.yaml directly into (EnrichedTerm, TermCandidate) pairs,
skipping extract and enrich entirely - there is nothing to extract from
a repo file, and no LLM draft to ground, because a human already wrote
the knowledge object.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from pipeline_service.candidate import Confidence
from pipeline_service.candidate import SourceType
from pipeline_service.candidate import TermCandidate
from pipeline_service.enriched_term import EnrichedTerm

DEFAULT_CURATED_TERMS_PATH = Path(__file__).parent / "curated_terms.yaml"


def load_curated_terms(
    path: Path = DEFAULT_CURATED_TERMS_PATH,
) -> tuple[tuple[EnrichedTerm, TermCandidate], ...]:
    """Parse every entry in the curated YAML file. Each entry is
    EnrichedTerm's own shape (a human wrote the definitions directly),
    paired with a TermCandidate carrying CURATED provenance so it flows
    through validate and load the same as any other source.

    Pydantic validation failures propagate - a malformed hand-written
    entry is a bug in the seed file, not something to skip silently.
    """
    raw_entries = yaml.safe_load(path.read_text()) or []
    results: list[tuple[EnrichedTerm, TermCandidate]] = []

    for entry in raw_entries:
        term = EnrichedTerm.model_validate(entry)
        candidate = TermCandidate(
            name=term.term,
            source_type=SourceType.CURATED,
            source_file=str(path),
            confidence=Confidence.CURATED,
        )
        results.append((term, candidate))

    return tuple(results)
