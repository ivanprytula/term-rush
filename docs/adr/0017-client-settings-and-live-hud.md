# ADR-0017: Client settings and live HUD

- **Status:** Accepted
- **Date:** 2026-09-22
- **Referenced from:** `services/web/src/App.tsx`, `GET /game-config`

## Context

The React client needs browser-local preferences and a live view of round
progress. Several values were previously duplicated in the UI: Sprint duration
options, survival lives, daily term count, answer length, and rubric weights.
The backend already owns these rules in `domain.constants` and validates Sprint
round creation through `CreateRoundRequest.duration_seconds`.

Voice language is different: it is a browser capability and user preference,
not gameplay state. Difficulty is not included because the current API has no
player-facing difficulty-selection contract.

## Decision

Expose one read-only REST resource, `GET /game-config`, for client-facing
gameplay limits and capabilities. Its response includes:

- mode capabilities and terminal limits;
- Sprint duration bounds, default, and supported options;
- Survival lives and Daily 20 term count;
- answer maximum length and score maximum;
- rubric weights.

The React client fetches this resource once per page load. It uses the response
for validation and display, with conservative fallback values so a temporary
configuration failure does not make the client unusable. The typed client is
generated from the service's OpenAPI schema.

Theme, voice language, and selected Sprint duration remain browser-local
preferences in `localStorage`. The selected Sprint duration is sent through the
existing `POST /game-rounds` `duration_seconds` field; no new persistence or
server preference endpoint is needed.

The live HUD derives cumulative score from returned answer scores and derives
streak from consecutive `Correct` verdicts. `Partial` and `Incorrect` reset
the streak. Streak has no score bonus, so the HUD cannot diverge from server
scores or leaderboard totals.

## Alternatives considered

### Separate constant endpoints

Rejected. Multiple endpoints for lives, scoring, Sprint limits, and answer
bounds would increase round trips and fragment one client contract.

### A generic constants endpoint

Rejected. `/game-config` describes product capabilities rather than exposing
internal implementation names or every domain constant.

### GraphQL for this resource now

Rejected for this phase. The planned GraphQL BFF can aggregate `gameConfig`
with session-screen data later, but introducing GraphQL solely for configuration
would add infrastructure before the aggregation problem exists. REST remains
the canonical resource boundary.

### Client-only configuration

Rejected for gameplay rules. Duplicated limits can drift from validation and
produce a misleading UI. Browser preferences remain client-only because they
are not server-owned gameplay rules.

## Consequences

- Backend constants remain the source of truth for gameplay limits.
- The frontend has one configuration request instead of duplicating each rule.
- The generated OpenAPI client must be regenerated when the config schema
  changes.
- Configuration loading adds one small read-only request at startup.
- The GraphQL BFF, when implemented, may compose this REST-owned read model
  without moving ownership into GraphQL.

## What this does not solve

- Difficulty selection or server-side difficulty filtering.
- Falling-term arcade gameplay.
- Authenticated synchronization of browser preferences across devices.
- Server-owned streak state; the current HUD is a view of the current round's
  recorded answers.

## When I would change this

- If the client needs to combine configuration with multiple session-screen
  resources, expose `gameConfig` through the planned GraphQL BFF while keeping
  game-service as the owner.
- If users can sign in and expect preferences across devices, move theme,
  voice language, and Sprint duration into authenticated user preferences.
- If difficulty becomes a player-facing mode, add an explicit validated
  difficulty contract to the round API and include its capabilities here.
- If config becomes versioned or tenant-specific, add an explicit config
  version or scope rather than silently changing the response semantics.
