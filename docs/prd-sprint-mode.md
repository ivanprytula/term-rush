# PRD: Sprint mode

- **Tag:** Both —
  <!-- Product: timed rounds are core to the learning-product vision
  (engagement, urgency). Skills-practice: real-time game loop,
  server-vs-client state split, currently ⏳ P1 unbuilt rows in
  skills-map.md. -->
- **Status:** Shipped — backend (`RoundMode`, timer fields, expiry
  rejection, LLM-grading suppression) and frontend (mode toggle,
  requestAnimationFrame countdown, time's-up screen) both merged; see
  [docs/ports-and-adapters.md](ports-and-adapters.md) for the request
  trace and PR #7.

## Problem

Today's loop has no game attrs at all — no timer, no win-condition, no end
state. It's "one term at a time, graded, repeat," capped only by
`ROUND_MAX_ANSWERS` as a safety ceiling, not a game design. README has
promised Sprint/Survival/Boss Round/Daily 20 since Phase 1; none exist.
Sprint is the smallest of the four: a countdown timer and a time-expires
win-condition, no lives/escalation to design around. It's the right first
mode because it proves the timer + end-state plumbing that Survival and
Boss Round will both need to build on.

## Decision

A round can optionally be created in **Sprint mode**: a fixed-duration
countdown (default 60s) starts on round creation; the round transitions
to a terminal `ended` state when the timer expires (server-authoritative —
see Decisions closed), independent of `ROUND_MAX_ANSWERS`. Score for the
run is the sum of graded answers submitted before expiry. Existing untimed
play (today's only mode) becomes **Classic mode** — the default.

**Note (post-rename):** a separate rename landed `Session` → `GameRound`
and made every round — Classic or Sprint — require an explicit `POST
/game-rounds` call before any answer can be submitted (removing the old
implicit "create on first answer" path entirely, not just for Sprint).
This PRD's original "Sprint is additive, Classic keeps its lazy-create
path" framing is superseded by that decision — both modes now share one
creation flow, differing only in whether `duration_seconds` is set.

## Non-goals

- Survival, Boss Round, Daily 20 — later modes, not scoped here.
- Leaderboards / persisted best-times — no ranking or cross-round
  comparison this phase; Sprint produces one run's final score, nothing
  more.
- Difficulty scaling within a Sprint run — every term drawn the same way
  Classic draws them (round-scoped exclusion, no weighting).
- Pause/resume — a Sprint run is continuous once started.

## Requirements

- **Must:** `GameRound` gains a mode (`classic` | `sprint`) and, for
  Sprint, a `started_at` + fixed `duration_seconds`. Deriving
  `ended`/`remaining` from those two fields, not a stored countdown, keeps
  `GameRound` frozen like it is today.
- **Must:** `SubmitAnswer` rejects a submission once a Sprint round has
  expired (422, not a silent no-op) — mirrors the existing `RoundFull`
  pattern in `round.py`.
- **Must:** API surfaces remaining time so the client can render a
  countdown without independently tracking wall-clock state — resolves the
  server-vs-client state split skills-map.md flags as unbuilt.
- **Should:** frontend timer uses `requestAnimationFrame`, not
  `setInterval`/CSS keyframes — skills-map.md already commits to this
  (`useGameLoop.ts`, "rAF, not CSS keyframes, because Survival needs
  runtime-variable acceleration").
- **Could:** a distinct terminal-state screen ("Time's up — final score: N")
  vs. reusing the existing per-answer result screen.

## Verification

- Unit: a round created with `mode=sprint, duration_seconds=60` accepts
  answers while `now < started_at + 60s`, rejects (422) after.
- Integration: `POST /game-rounds` with `mode=sprint` then `POST
  .../answers/submit` past expiry returns 422, not 200.
- Manual/E2E: start a Sprint round in the browser, let the timer expire,
  confirm submission is blocked and a final-score state renders.
- `just check` green; no regression to existing Classic-mode tests (Classic
  is `mode=classic`, unchanged behavior).

## Constraints & assumptions

- Depends on nothing outside `services/game` — no content-service or
  cross-service change needed; Sprint is purely a `GameRound`/
  `SubmitAnswer` concern.
- Assumes `ROUND_MAX_ANSWERS=200` remains a generous ceiling Sprint won't
  hit in 60s at realistic answer speed — no change needed there.

## Decisions closed

- **Timer authority: server-authoritative.** `started_at`/`duration_seconds`
  on `GameRound` are the source of truth; a submit arriving after expiry is
  rejected server-side (422) regardless of what the client's clock showed.
  Consistent with grading already being a protected trust boundary
  (ADR-0013) — a client clock is trivially manipulable.
- **LLM grading: deterministic-only in Sprint.** `use_llm_grading` is
  forced off when `mode=sprint`, regardless of what the client sends — SSE
  streaming latency works against a timed mode's point. LLM escalation
  stays Classic-only. `SubmitAnswer` (or the API layer) silently ignores
  the flag in Sprint rather than 422ing on it — a client that always sends
  `use_llm_grading=true` shouldn't need mode-aware logic to avoid an error.
- **Default duration: 60s.** Accepted as-is for now; revisit once real
  deterministic-grading latency is observed live.
- **Server mints the round id.** `POST /game-rounds` returns the new id —
  standard REST creation semantics, no client-supplied id, no collision
  case to design around.

## Open questions

None — all decisions closed for build.
