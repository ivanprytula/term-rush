"""Daily 20: a shared, deterministic term set for a calendar date.

Every player who starts a Daily 20 round on the same UTC date draws from the
same 20 (or fewer, if the bank is smaller) terms, in the same order — a
shared puzzle, not a per-round random draw.
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Sequence
from datetime import date

from game_service.domain import constants


def daily_seed(day: date) -> int:
    """Deterministic seed for a calendar date.

    sha256 of DAILY_20_SEED_EPOCH + the ISO date, truncated to fit an int —
    not Python's hash(), which is salted per-process and would give every
    replica (or even every restart) a different puzzle for the same date.
    """
    digest = hashlib.sha256(
        f"{constants.DAILY_20_SEED_EPOCH}:{day.isoformat()}".encode()
    )
    return int.from_bytes(digest.digest()[:8], "big")


def daily_term_ids(
    day: date, all_ids: Sequence[str], size: int = constants.DAILY_20_ROUND_SIZE
) -> tuple[str, ...]:
    """The day's shared term set: a seeded shuffle of the sorted full id
    list, truncated to size.

    Pure and total — the same (day, all_ids) always yields the same tuple,
    on any replica, in any process. all_ids need not be pre-sorted by the
    caller; sorting happens here so an unsorted input can't silently change
    the puzzle. A bank smaller than size degrades to "however many terms
    exist" rather than erroring.
    """
    sorted_ids = sorted(all_ids)
    rng = random.Random(daily_seed(day))
    return tuple(rng.sample(sorted_ids, k=min(size, len(sorted_ids))))
