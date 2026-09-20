# ADR-0007: Flat per-service layout, no src/, no service namespace

- **Status:** Superseded — see "Resolution" below
- **Date:** 2026-09-17
- **Supersedes:** the namespaced service layout discussed in ADR-0003

## Decision

`services/game/{domain,application,infrastructure,api}/` — no `src/`, no `game_service/`
wrapper directory. `from domain.term import Term`, not `from game_service.domain.term`.

This was an explicit choice against two things previously argued for:

- **`src/` as a packaging-correctness guard.** Real once `game-service` gained a build
  backend, but the payoff (catching a wheel that's missing a file before Docker does)
  was judged not worth the extra path segment for a project with one deploy artifact
  per ADR-0006.
- **`game_service` as a distinct namespace per service**, which is what let an
  import-linter contract forbid one service importing another. Traded away along with
  the **service-isolation contract itself**, which is dropped for now (see below).

## Consequence: service isolation is currently unenforced

With `domain`, `application`, `infrastructure`, `api` as bare top-level names, a second
service cannot also own those names without collision — so nothing currently stops
`content-service` (Phase 3) from importing `game-service`'s `domain` package if both
land in the same Python path.

Today this costs nothing: one service exists, and each runs in its own container per
ADR-0006, so there is no shared interpreter to collide in. It becomes a live question
the moment a second service is added.

## When I would change this

**The moment a second service is added**, pick one:

1. Reintroduce a per-service namespace (`game_service`, `content_service`) and restore
   the forbidden-imports contract — the mechanism from before this ADR, at the cost of
   one extra path segment per service.
2. Rely entirely on container boundaries: services never share a Python path in any
   real deployment, so the "import" collision is only possible in local tooling
  (a shared type-check run, a monorepo-wide lint), not in anything that ships. Accept that
   and skip the contract.

Option 1 is the likely pick if a reviewer would reasonably expect the contract to
exist; option 2 if the container boundary is judged sufficient proof on its own. Not
decided now — deferred to when the second service exists and the trade-off is concrete
instead of speculative.

## Resolution

The second service (`content-service`) landed and **option 1 was picked**:
both services now live under a per-service namespace (`game_service/`,
`content_service/`), and `services/*/pyproject.toml`'s
`[tool.importlinter]` sections enforce a real forbidden-imports contract
in both directions — `lint-imports` runs clean, verified with zero
cross-service imports found by direct grep as well as the tool itself.
The flat layout and the "isolation is currently unenforced" section
above describe a state that no longer exists; kept here for the
historical reasoning, not as current fact. See ADR-0009 for the
resulting `game_service` → `content_service` gRPC boundary this
contract now guards.
