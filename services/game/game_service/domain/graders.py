"""The grader chain.

Each grader may abstain by returning None, in which case the next one tries.
Ordering is cheapest-and-most-certain first, so the common case (a player types
the exact expansion) never touches the expensive path.

Phase 2 inserts an LLM rubric grader at the end of the chain. No caller changes:
that is the whole point of the abstain protocol.
"""

from __future__ import annotations

import re
from typing import Protocol

from . import constants
from .outcome import GradeOutcome
from .outcome import MatchedVia
from .outcome import RubricBreakdown
from .outcome import Verdict
from .term import Term

# Tuned against the prototype's behaviour; see tests/unit/test_graders.py which
# pins the original similarity() results as a regression oracle.
FUZZY_ACCEPT_THRESHOLD = 0.62
FUZZY_PARTIAL_THRESHOLD = 0.40
SUBSTRING_SIMILARITY = 0.88


def normalize(text: str) -> str:
    """Collapse to comparable form: lowercase, alphanumerics, single spaces.

    Ported verbatim in behaviour from the prototype's normalize() so existing
    matches keep working.
    """
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def token_similarity(answer: str, target: str) -> float:
    """Token-overlap similarity in [0, 1].

    Ported from the prototype's similarity(). Deliberately simple and
    deterministic: it is the free fallback that must keep working when the LLM
    judge is disabled, out of budget, or down.
    """
    a, b = normalize(answer), normalize(target)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return SUBSTRING_SIMILARITY

    tokens_a, tokens_b = set(a.split()), set(b.split())
    hits = len(tokens_a & tokens_b)
    return hits / max(len(tokens_a), len(tokens_b))


class Grader(Protocol):
    """One step in the evaluation chain.

    Returns None to abstain — meaning "I have no opinion, ask the next grader" —
    rather than returning a zero score, which would end the chain.
    """

    @property
    def matched_via(self) -> MatchedVia: ...

    def grade(self, answer: str, term: Term) -> GradeOutcome | None: ...


class ProfanityCheckerPort(Protocol):
    """Detects offensive content. Implemented by an infrastructure adapter
    wrapping a wordlist library — declared here, not in application/ports.py,
    for the same reason as LLMJudgePort: it's a domain-level collaborator,
    not an application-owned contract.
    """

    def is_offensive(self, text: str) -> bool: ...


class ProfanityGrader:
    """Rejects offensive answers before any other grader sees them.

    First in the chain deliberately: cheap (local wordlist lookup, no I/O)
    and unconditional — an offensive answer is never worth scoring on
    correctness. Abstains (returns None) for clean answers, same as every
    other non-terminal grader.
    """

    def __init__(self, checker: ProfanityCheckerPort) -> None:
        self._checker = checker

    @property
    def matched_via(self) -> MatchedVia:
        return MatchedVia.FLAGGED

    def grade(self, answer: str, term: Term) -> GradeOutcome | None:
        if not self._checker.is_offensive(answer):
            return None
        return GradeOutcome(
            verdict=Verdict.INCORRECT,
            rubric=RubricBreakdown.zero(),
            matched_via=MatchedVia.FLAGGED,
            confidence=1.0,
            feedback="Let's keep it clean — try explaining the term instead.",
        )


class ExactGrader:
    """Exact match against the canonical expansion after normalization."""

    @property
    def matched_via(self) -> MatchedVia:
        return MatchedVia.EXACT

    def grade(self, answer: str, term: Term) -> GradeOutcome | None:
        if normalize(answer) != normalize(term.expansion):
            return None
        return GradeOutcome(
            verdict=Verdict.CORRECT,
            rubric=RubricBreakdown.expansion_only(),
            matched_via=MatchedVia.EXACT,
            confidence=1.0,
            feedback=f"{term.term} = {term.expansion}.",
        )


class AliasGrader:
    """Match against any accepted alias spelling."""

    @property
    def matched_via(self) -> MatchedVia:
        return MatchedVia.ALIAS

    def grade(self, answer: str, term: Term) -> GradeOutcome | None:
        normalized = normalize(answer)
        for alias in term.aliases:
            if normalized == normalize(alias):
                return GradeOutcome(
                    verdict=Verdict.CORRECT,
                    rubric=RubricBreakdown.expansion_only(),
                    matched_via=MatchedVia.ALIAS,
                    confidence=0.95,
                    feedback=f"{term.term} = {term.expansion}. "
                    f'"{alias}" is an accepted spelling.',
                )
        return None


class FuzzyGrader:
    """Token-overlap match, tolerant of word order and minor wording drift.

    Never abstains: it is the last deterministic grader, so it must always
    produce a verdict rather than leaving the chain empty-handed.
    """

    @property
    def matched_via(self) -> MatchedVia:
        return MatchedVia.FUZZY

    def grade(self, answer: str, term: Term) -> GradeOutcome | None:
        best = max(
            token_similarity(answer, candidate)
            for candidate in term.all_acceptable_expansions()
        )

        if best >= FUZZY_ACCEPT_THRESHOLD:
            return GradeOutcome(
                verdict=Verdict.CORRECT,
                rubric=RubricBreakdown.expansion_only(),
                matched_via=MatchedVia.FUZZY,
                confidence=best,
                feedback=f"{term.term} = {term.expansion}. {term.primary_definition}",
            )

        if best >= FUZZY_PARTIAL_THRESHOLD:
            return GradeOutcome(
                verdict=Verdict.PARTIAL,
                rubric=RubricBreakdown(
                    concept=0,
                    expansion=int(constants.EXPANSION_WEIGHT * best),
                    purpose=0,
                    example=0,
                ),
                matched_via=MatchedVia.FUZZY,
                confidence=best,
                feedback=f"Close. {term.term} = {term.expansion}. "
                f"{term.primary_definition}",
            )

        return GradeOutcome(
            verdict=Verdict.INCORRECT,
            rubric=RubricBreakdown.zero(),
            matched_via=MatchedVia.FUZZY,
            confidence=1.0 - best,
            feedback=f"{term.term} = {term.expansion}. {term.primary_definition}",
        )


class AnswerEvaluator:
    """Runs the grader chain and returns the first non-abstaining outcome."""

    def __init__(self, graders: tuple[Grader, ...]) -> None:
        if not graders:
            raise ValueError("AnswerEvaluator needs at least one grader")
        self._graders = graders

    def evaluate(self, answer: str, term: Term) -> GradeOutcome:
        for grader in self._graders:
            outcome = grader.grade(answer, term)
            if outcome is not None:
                return outcome

        # Only reachable if the chain's final grader abstains, which the
        # deterministic chain never does. Treated as a programming error.
        raise RuntimeError(
            f"no grader produced an outcome for term {term.id!r}; "
            "the final grader in the chain must never abstain"
        )


def build_deterministic_evaluator(
    profanity_checker: ProfanityCheckerPort | None = None,
) -> AnswerEvaluator:
    """The Phase 1 chain, and the permanent fallback when the LLM is unavailable.

    profanity_checker: opt-in. None (the default) omits ProfanityGrader
    entirely — the chain is Exact/Alias/Fuzzy exactly as in Phase 1. Passing
    a real ProfanityCheckerPort implementation (infrastructure adapter,
    constructed by the caller — this module stays framework-free per
    ADR-0003) prepends ProfanityGrader as the first, unconditional check.
    """
    graders: tuple[Grader, ...] = (ExactGrader(), AliasGrader(), FuzzyGrader())
    if profanity_checker is not None:
        graders = (ProfanityGrader(profanity_checker), *graders)
    return AnswerEvaluator(graders)
