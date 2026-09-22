# ADR-0016: Game mode terminal states

- **Status:** Accepted
- **Date:** 2026-09-22
- **Referenced from:** `domain/round.py`, `domain/daily.py`, `domain/term.py`

## Context

Four game modes now exist (Classic, Sprint, Survival, Boss Round, Daily
20 — five, counting Classic), each with its own way of deciding a round is
over: a clock (Sprint), a lives counter (Survival), an answer count of one
(Boss Round), an answer count of twenty (Daily 20). Building these as
Survival → Boss Round → Daily 20, in that order, meant every later mode
could reuse whatever the first one got right — or repeat whatever it got
wrong. Four decisions were made once, at Survival's design time, and held
for the rest:

## Decisions

### 1. Terminal state is derived, not a stored `ended` flag

`GameRound` stays frozen (pydantic, `model_config = {"frozen": True}`).
Every mode's "is this round over" question — `is_over(now)` — is answered
by looking at `self.answers`, `self.mode`, and (for Sprint) `self.started_at`/
`self.duration_seconds`, never by flipping a stored boolean when a
terminal condition first fires. This matches `remaining_seconds` and
`lives_remaining`'s existing pattern: a value computed fresh from the
answer log every time, not cached and risking drift from it.

Rejected alternative: a stored `ended: bool` field, set once and checked
thereafter. Rejected because it introduces a second source of truth that
must be kept in sync with `answers` on every `record()` call — a forgotten
update site is a real bug (a round reporting `ended=False` after its
20th Daily-20 answer, say), whereas a derived property cannot drift by
construction.

### 2. One `RoundOver` exception, not one per mode

Survival's lives-exhausted, Boss Round's one-answer-done, and Daily 20's
cap-reached conditions all raise the same `RoundOver` exception. A caller
(the API's exception handler, in particular) doesn't need to distinguish
*why* a round ended to return the right 422 — "the round is over" is the
only fact that matters at that boundary.

Sprint keeps its own, pre-existing `RoundExpired` rather than being folded
into `RoundOver` retroactively. It predates this ADR, has its own
established 422 contract, and a timer running out is a genuinely distinct
kind of "over" (time-based, not answer-count-based) — not worth the churn
of renaming an already-shipped, already-tested exception for the sake of
uniformity alone.

Rejected alternative: `LivesExhausted`, `BossRoundComplete`,
`DailyRoundFull` as three separate exceptions. Rejected because nothing
downstream ever needs to tell them apart — they'd exist only to be caught
by the same handler and turned into the same 422, which is what one
exception already does.

### 3. Boss-eligibility crosses the wire as generic content predicates

`Term.is_boss_eligible` (HARD difficulty, has examples, >40-char
definition) is a game-service domain rule. The proto and content-service
change needed to serve a boss-eligible term does *not* expose that rule or
its name — instead, `GetRandomRequest` gained three generic, reusable
fields: `min_difficulty`, `require_examples`, `min_definition_length`.
Content-service filters on content properties it already owns; it never
learns what a "Boss Round" is, and the same three fields compose for any
future mode that needs a different content-level constraint, without a
fourth RPC field per mode.

Rejected alternative: a single `boss_eligible: bool` field. Rejected
because it would require content-service to either duplicate
game-service's eligibility rule (a second place that rule could drift from
`Term.is_boss_eligible`) or call back into game-service to evaluate it
(a network round-trip for a filter that's just three comparisons) —
neither is as clean as content-service simply owning the predicates it
already has the data for.

### 4. Daily 20's seed lives in a pure domain function, not inside content-service

`daily.py`'s `daily_seed(day)` and `daily_term_ids(day, all_ids, size)` are
stdlib-only (`hashlib`, `random.Random`), framework-free, and callable
without either service running. Content-service exposes only
`ListTermIds` — every term id, sorted — and the seeding/shuffling happens
in game-service's domain layer.

Rejected alternative: a `GetDaily(date)` RPC computed inside
content-service, returning the day's 20 term objects directly. Rejected
for the same reason as (3): it would make content-service know what
"Daily 20" is, when the only thing it actually needs to provide is "every
id, in a stable order."

## What this does not solve

Snapshotting the day's 20 ids onto `GameRound.term_ids` at creation makes
one round internally self-consistent, but does not guarantee two players
see an identical puzzle if a term is published mid-day between their two
round-creations — there's no login, so there's no durable per-player state
to reconcile against regardless.

## When I would change this

- If a sixth mode needs a terminal condition that genuinely isn't "answer
  count/lives/clock hit some threshold" (e.g. an opponent-driven end
  condition in a future multiplayer mode), `RoundOver` may need to carry a
  reason code rather than staying a bare exception — revisit only when
  that mode is actually being designed, not preemptively.
- If content-service ever needs a fourth content-level filter dimension
  beyond the three `TermFilter` fields, extend `TermFilter` and the proto
  message rather than introducing a second filter mechanism.
- If Daily 20 ever needs a true per-player "already played" lock, that
  requires login first (out of scope today) — the seeding function itself
  would not need to change, only how the client gates a repeat play.
