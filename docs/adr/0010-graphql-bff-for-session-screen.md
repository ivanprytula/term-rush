# ADR-0010: GraphQL BFF for the session screen

- **Status:** Accepted
- **Date:** 2026-09-23
- **Referenced from:** `services/web/src/App.tsx`, `GET /game-config`,
  `GET /terms/random`, `GET /terms/categories`

## Context

Loading the session screen fires three independent read requests before a
player can see a term: `GET /game-config` (mode capabilities, Sprint bounds,
rubric weights), `GET /terms/categories` (the category picker's options),
and `GET /terms/random` (the first term). Each is a separate round trip, each
can fail independently, and the client already has to coordinate three
loading/error states for what is conceptually one screen's worth of data.

`POST /game-rounds` (minting a round) is not part of this problem — it is a
mutation with a side effect (a written row, a server-generated id), not a
read the client can batch away. Collapsing reads and mutations into one
GraphQL operation would blur that distinction for no benefit.

## Decision

Add a GraphQL BFF (Strawberry) that exposes one query, `sessionScreen`,
aggregating the three existing REST reads:

```graphql
query SessionScreen($category: String) {
  sessionScreen(category: $category) {
    gameConfig {
      modes { mode maxAnswers timed llmGrading }
      sprint { ... }
      rubric { ... }
    }
    termCategories { slug label }
    randomTerm(category: $category) { termId prompt difficulty }
  }
}
```

The BFF is a thin router mounted inside `game-service` (`api/graphql/`), not
a separate deployable service. It has no domain logic of its own — each
field resolver calls the same use cases (`GetNextTerm`, `ListTermCategories`)
and reads the same `domain.constants` the REST routers already call. REST
endpoints are not removed: `/game-config`, `/terms/random`, and
`/terms/categories` stay, both because other consumers may want single-
resource REST semantics and because the REST resource boundary remains
canonical (per ADR-0017) — GraphQL composes it, it doesn't replace it.

Mutations (`POST /game-rounds`, `POST /game-rounds/{id}/answers/submit`,
its SSE variant) stay REST. GraphQL subscriptions could model the SSE
streaming path, but that's a separate decision with its own trade-offs, not
required to solve the session-screen round-trip problem this ADR is scoped
to.

## Alternatives considered

### A separate `bff` service, its own deployable

Rejected for now. There is no team boundary or independent scaling need
that justifies a second process and second Docker image — it would be
skills-practice theater (ADR-0001's own criterion) rather than a real
architectural need. Revisit if game-service's REST and GraphQL surfaces
ever need to scale or deploy independently.

### REST response embedding (`?embed=categories,term`)

Rejected. Ad-hoc embedding parameters reproduce GraphQL's field-selection
problem without its tooling (typed schema, codegen, introspection) and tend
to accrete inconsistent embedding rules per endpoint over time.

### Do nothing; keep three client-side `Promise.all` calls

Rejected as the long-term answer, acceptable as what's shipped today. Three
round trips is a real but small cost at current scale — this ADR exists
because the roadmap already commits to closing it and because it's the
correct place to demonstrate one query replacing several REST round-trips
(see skills-map.md's API design row), not because the current latency is
unacceptable.

## Consequences

- One new dependency: `strawberry-graphql` (or `strawberry-graphql[fastapi]`)
  in `services/game/pyproject.toml`.
- `RoundMode` needs a GraphQL-owned mirror (`api/graphql/types.RoundMode`).
  GraphQL enums serialize by Python member name, not `.value` — reusing
  the domain `StrEnum` directly would make the wire value `CLASSIC` while
  REST's `GameModeConfigResponse.mode` emits `"classic"` (`StrEnum.value`).
  The mirror's members are named in lowercase so both surfaces agree; this
  is deliberately duplicated, not shared, to keep GraphQL's schema free of
  a REST-specific enum-casing dependency.
- `api/graphql/` becomes a new module inside `game-service`'s API layer;
  import-linter's layering contract (`api -> infrastructure -> application
  -> domain`) applies to it exactly as it does to the REST routers — no new
  contract needed, only new rows covered by the existing one.
- The frontend needs a GraphQL client (or a hand-rolled `fetch` against
  `/graphql`, given there's exactly one query to start) alongside the
  existing generated REST client.
- Two schemas (OpenAPI + GraphQL) now describe overlapping data. Field
  names and types must be kept in sync by hand until/unless codegen ties
  them together — a manual step, tracked here rather than solved silently.

## What this does not solve

- Server-owned mutations, subscriptions, or an auth-scoped schema — no
  login exists yet.
- Consolidating the REST resources themselves. `/game-config`,
  `/terms/random`, and `/terms/categories` remain the source of truth;
  GraphQL is a read aggregation layer on top, not a replacement.
- N+1 or resolver-level performance concerns — the query graph is flat
  (three independent fields, no nested per-item resolution) so a
  DataLoader isn't needed at this shape.

## When I would change this

- If GraphQL fields and REST schemas drift in practice (a rename in one not
  mirrored in the other causing a bug), introduce shared Pydantic-to-
  GraphQL type generation rather than hand-syncing indefinitely.
- If a mutation genuinely benefits from GraphQL's typed input/output over
  REST (e.g. a multi-step round-creation flow), reopen the "mutations stay
  REST" decision then — not preemptively.
- If game-service's GraphQL and REST surfaces need independent scaling or
  ownership, split the BFF into its own service — the same trigger as
  content-service's split in ADR-0007.
