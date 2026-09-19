"""better-profanity-fast adapter for ProfanityCheckerPort.

Rust-backed, API-compatible with the original better-profanity. Wordlist-
based, not ML: deterministic and instant, matching why it's the first
grader in the chain (domain/graders.py). Known limitation: a curated
wordlist is never exhaustive and won't catch every evasion (leetspeak,
unlisted slurs in other languages). Acceptable for Phase 2's scope — this is
a moderation floor, not a full trust-and-safety pipeline.
"""

from __future__ import annotations

from better_profanity_fast import profanity


class BetterProfanityChecker:
    """ProfanityCheckerPort implementation backed by better-profanity-fast."""

    def __init__(self) -> None:
        profanity.load_censor_words()

    def is_offensive(self, text: str) -> bool:
        return profanity.contains_profanity(text)
