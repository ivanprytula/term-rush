"""Deterministic four-slice rubric scoring.

Awards concept/purpose/example by content overlap against the term's own
knowledge object. Not semantic understanding — the Phase 2 LLM judge replaces
this — but enough signal that the rubric is live from Phase 1 rather than
capped at the 30-point expansion slice.
"""

from __future__ import annotations

from . import constants
from .graders import normalize
from .graders import token_similarity
from .outcome import RubricBreakdown
from .term import Term

# Words carrying no domain signal. Overlap on these is noise, so they are
# stripped before scoring content slices.
STOPWORDS = frozenset(
    (
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "it",
        "its",
        "this",
        "that",
        "these",
        "those",
        "of",
        "for",
        "to",
        "in",
        "on",
        "at",
        "by",
        "with",
        "from",
        "as",
        "and",
        "or",
        "but",
        "if",
        "then",
        "than",
        "so",
        "such",
        "what",
        "which",
        "when",
        "where",
        "who",
        "whom",
        "how",
        "why",
        "can",
        "could",
        "may",
        "might",
        "will",
        "would",
        "shall",
        "should",
        "must",
        "do",
        "does",
        "did",
        "done",
        "have",
        "has",
        "had",
        "having",
        "you",
        "your",
        "they",
        "them",
        "their",
        "we",
        "our",
        "i",
        "me",
        "my",
        "he",
        "she",
        "his",
        "her",
        "not",
        "no",
        "yes",
    )
)

# Phrases signalling the player is explaining *why* something exists rather
# than only what it is. Purpose is the slice most often skipped.
PURPOSE_MARKERS = (
    "used to",
    "used for",
    "so that",
    "in order to",
    "allows",
    "enables",
    "lets you",
    "helps",
    "prevents",
    "avoids",
    "ensures",
    "guarantees",
    "solves",
    "purpose",
    "because",
    "instead of",
    "rather than",
    "useful",
    "benefit",
    "advantage",
    "makes it",
)

# Phrases signalling a concrete instance.
EXAMPLE_MARKERS = (
    "for example",
    "e g",
    "eg",
    "such as",
    "like when",
    "for instance",
    "example",
    "say you",
    "imagine",
    "consider",
)

MIN_CONTENT_WORDS = 4
CONCEPT_FULL_OVERLAP = 0.45
EXAMPLE_OVERLAP = 0.25


def content_words(text: str) -> frozenset[str]:
    """Meaningful tokens: normalized, stopworded, length-filtered."""
    return frozenset(
        word
        for word in normalize(text).split()
        if word not in STOPWORDS and len(word) > 2
    )


def _overlap(answer_words: frozenset[str], target: str) -> float:
    """Fraction of the target's content words the answer covers."""
    target_words = content_words(target)
    if not target_words:
        return 0.0
    return len(answer_words & target_words) / len(target_words)


def _contains_marker(answer: str, markers: tuple[str, ...]) -> bool:
    padded = f" {normalize(answer)} "
    return any(f" {m} " in padded for m in markers)


def score_expansion(answer: str, term: Term) -> int:
    """Best similarity against the expansion and its aliases, scaled to weight."""
    best = max(
        token_similarity(answer, candidate)
        for candidate in term.all_acceptable_expansions()
    )
    return round(constants.EXPANSION_WEIGHT * best)


def score_concept(answer: str, term: Term) -> int:
    """Overlap against the term's definitions."""
    words = content_words(answer)
    if len(words) < MIN_CONTENT_WORDS:
        return 0

    best = max(_overlap(words, d) for d in term.definitions)
    ratio = min(best / CONCEPT_FULL_OVERLAP, 1.0)
    return round(constants.CONCEPT_WEIGHT * ratio)


def score_purpose(answer: str, term: Term) -> int:
    """Purpose language plus definition overlap.

    Requires both: marker phrases alone are cheap to fake, and overlap alone
    does not distinguish "what it is" from "what it is for".
    """
    if not _contains_marker(answer, PURPOSE_MARKERS):
        return 0

    words = content_words(answer)
    if len(words) < MIN_CONTENT_WORDS:
        return 0

    best = max(_overlap(words, d) for d in term.definitions)
    ratio = min(best / CONCEPT_FULL_OVERLAP, 1.0)
    # Half for signalling purpose at all, half for grounding it.
    return round(constants.PURPOSE_WEIGHT * (0.5 + 0.5 * ratio))


def score_example(answer: str, term: Term) -> int:
    """Explicit example marker, or overlap with a stored example."""
    words = content_words(answer)
    if len(words) < MIN_CONTENT_WORDS:
        return 0

    if _contains_marker(answer, EXAMPLE_MARKERS):
        return constants.EXAMPLE_WEIGHT

    if (
        term.examples
        and max(_overlap(words, e) for e in term.examples) >= EXAMPLE_OVERLAP
    ):
        return constants.EXAMPLE_WEIGHT

    return 0


def score(answer: str, term: Term) -> RubricBreakdown:
    return RubricBreakdown(
        expansion=score_expansion(answer, term),
        concept=score_concept(answer, term),
        purpose=score_purpose(answer, term),
        example=score_example(answer, term),
    )
