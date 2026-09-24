"""Extract candidate terms from PDF documents in the intake directory
(ADR-0018's document/OCR source, Low confidence).

Secondary consumer of document ingestion (ADR-0018): the primary output is
the chunked RAG corpus (document_ingestion.chunking); this extractor pulls
capitalized/acronym-shaped tokens out of the same OCR'd text the same way
adr_headings.py pulls identifier-shaped spans - free text has no backtick
convention, so token shape is the only signal available.
"""

from __future__ import annotations

import re
from pathlib import Path

from pipeline_service.candidate import Confidence
from pipeline_service.candidate import SourceType
from pipeline_service.candidate import TermCandidate
from pipeline_service.document_ingestion.document_text import extract_text_from_document
from pipeline_service.document_ingestion.document_text import find_intake_documents

__all__ = [
    "extract_document_sources",
    "extract_from_document",
    "find_intake_documents",
]

_TERM_LIKE = re.compile(r"\b[A-Z][A-Za-z0-9]{2,}\b")

# Free text has no backlick convention like ADR headings do, so shape alone
# (capitalized, 3+ chars) also matches ordinary sentence-starting words.
# This is not an exhaustive stopword list - it filters the common function
# words that shape alone can't distinguish from real terms. LOW confidence
# and mandatory review (ADR-0018) absorb what still gets through.
_SENTENCE_STARTERS = frozenset(
    {
        "The",
        "This",
        "That",
        "These",
        "Those",
        "It",
        "Its",
        "There",
        "Here",
        "When",
        "Where",
        "While",
        "After",
        "Before",
        "Then",
        "Later",
        "Also",
        "However",
        "Therefore",
        "Please",
        "Note",
        "For",
        "And",
        "But",
        "With",
        "From",
        "Any",
        "All",
        "Each",
    }
)


def extract_from_document(path: Path) -> tuple[TermCandidate, ...]:
    """Parse one PDF into candidates, one per distinct capitalized token."""
    text = extract_text_from_document(path)

    candidates: dict[str, TermCandidate] = {}
    for name in _TERM_LIKE.findall(text):
        if name in _SENTENCE_STARTERS:
            continue
        candidates.setdefault(
            name,
            TermCandidate(
                name=name,
                source_type=SourceType.DOCUMENT_OCR,
                source_file=str(path),
                confidence=Confidence.LOW,
            ),
        )

    return tuple(candidates.values())


def extract_document_sources(intake_dir: Path) -> tuple[TermCandidate, ...]:
    """Extract candidates from every PDF in the intake directory,
    deduplicated by name (a term appearing in multiple documents yields
    one candidate, keeping the first document it was seen in).
    """
    seen: dict[str, TermCandidate] = {}
    for path in find_intake_documents(intake_dir):
        for candidate in extract_from_document(path):
            seen.setdefault(candidate.name, candidate)
    return tuple(seen.values())
