"""Extract candidate terms from ADR headings (ADR-0004's Medium-confidence
"ADR + doc headings" source).

Deterministic, no LLM (ADR-0004's Extract stage). Most heading text is
prose, not vocabulary ("Why this is the right shape for the project") -
ADR-0004 names this source's own failure mode. Backtick-quoted spans
inside `###` headings are the reliable signal instead: ADR authors already
mark identifiers that way (`RoundOver`, `ANTHROPIC_API_KEY`, `bff`), so
extraction reuses that convention rather than guessing at heading shape.
`##` headings are skipped entirely - every ADR reuses the same boilerplate
section names (Context, Decision, Consequences), which are structure, not
content.
"""

from __future__ import annotations

import re
from pathlib import Path

from pipeline_service.candidate import Confidence
from pipeline_service.candidate import SourceType
from pipeline_service.candidate import TermCandidate

_H3_HEADING = re.compile(r"^###\s+(.+)$", re.MULTILINE)
_BACKTICKED = re.compile(r"`([^`]+)`")
_IDENTIFIER_LIKE = re.compile(r"^[A-Za-z][A-Za-z0-9_.]*$")


def find_adr_files(repo_root: Path) -> tuple[Path, ...]:
    """Every ADR in docs/adr/, sorted for deterministic ordering."""
    return tuple(sorted((repo_root / "docs" / "adr").glob("*.md")))


def extract_from_adr(path: Path) -> tuple[TermCandidate, ...]:
    """Parse one ADR's `###` headings for backtick-quoted identifiers.

    A URL fragment or query string (`/ready`, `?embed=categories,term`)
    is also backtick-quoted in prose but isn't a term - filtered by
    requiring an identifier shape (leading letter, alnum/underscore/dot).
    """
    text = path.read_text()
    candidates: dict[str, TermCandidate] = {}

    for heading_match in _H3_HEADING.finditer(text):
        heading = heading_match.group(1)
        for name in _BACKTICKED.findall(heading):
            if not _IDENTIFIER_LIKE.match(name):
                continue
            candidates.setdefault(
                name,
                TermCandidate(
                    name=name,
                    source_type=SourceType.ADR_HEADING,
                    source_file=str(path),
                    confidence=Confidence.MEDIUM,
                ),
            )

    return tuple(candidates.values())


def extract_adr_headings(repo_root: Path) -> tuple[TermCandidate, ...]:
    """Extract candidates from every ADR, deduplicated by name (a term
    named in multiple ADRs yields one candidate, keeping the first ADR
    it was seen in).
    """
    seen: dict[str, TermCandidate] = {}
    for path in find_adr_files(repo_root):
        for candidate in extract_from_adr(path):
            seen.setdefault(candidate.name, candidate)
    return tuple(seen.values())
