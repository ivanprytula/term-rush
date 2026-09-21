# ADR-0009: gRPC for game-service to content-service Term Lookup

- **Status:** Accepted
- **Date:** 2026-09-21
- **Relates to:** ADR-0007 (service isolation, namespace resolution),
  ADR-0011 (Kafka cache invalidation)

## Context

Phase 3a split term ownership into `content-service`, its own Postgres
database, per ADR-0007's Resolution. `game-service` no longer has a local
`terms` table — every grading request needs `content-service`'s term data
to score an answer, and every new round needs a random term to serve.

This is a different shape of call than the REST endpoints elsewhere in the
stack: internal-only (never called from the browser), high-frequency (once
per answer submitted, not once per page load), and schema-first (both
services already share `Term`'s field set, just in two now-separate
domains).

## Decision

`game-service` calls `content-service` over gRPC, not REST, for term
lookup specifically — this is a per-hop choice, not a stack-wide one; REST
stays for every browser-facing endpoint.

`libs/term-proto/` owns `term.proto` (content-service is the producer of
the contract) and its generated Python stubs, **committed**, not
generated at build time — a reviewer cloning the repo gets a working
client/server pair without running codegen first.

```protobuf
service TermService {
  rpc GetById(GetByIdRequest) returns (TermReply);
  rpc GetRandom(GetRandomRequest) returns (TermReply);
}
```

`TermReply.found: bool` models "not found" as a field, not a gRPC error
status — this preserves `TermRepository.by_id -> Term | None` on the
client (`game_service/infrastructure/grpc_term_repository.py`) without the
call site needing to catch a not-found-shaped exception.

### Why gRPC over REST for this hop

- **Schema-first fits an internal contract.** Both services already agree
  on `Term`'s shape; protobuf makes that agreement machine-checked instead
  of two independently-maintained Pydantic models drifting apart.
- **Latency-sensitive, high-frequency.** Every graded answer does a lookup;
  gRPC's binary framing and HTTP/2 multiplexing beat REST/JSON's per-call
  overhead at this call volume.
- **Never crosses a browser boundary**, so REST's actual advantages here —
  human-readable payloads, curl-ability, browser-native fetch — buy
  nothing. The place those advantages matter (`services/web/` talking to
  `game-service`) stays REST.

### GrpcTermRepository: same port, no use-case change

`GrpcTermRepository` implements the existing `TermRepository` ABC
(`game_service/application/ports.py`) — the same seam `SQLTermRepository`
used to satisfy. No use-case code changed when the adapter swapped; this
is the port/adapter boundary doing its job.

- **Cache:** `by_id` keeps a bounded in-process dict keyed by `term_id`,
  TTL 300s — grading calls `by_id` for the same term repeatedly within a
  round, and this keeps that off the network after the first lookup.
  `random` is never cached (caching a "give me anything" call defeats its
  purpose).
- **Fallback:** on an RPC failure, `by_id` prefers a stale cache hit over
  failing the request outright; only returns `None` if the cache is empty
  *and* the RPC fails. `random` has no fallback — content-service being
  down means there is genuinely no term to serve, so `GetRandomTerm`
  propagates that as `ValueError` the same way a not-found term already
  does.
- **Staleness backstop:** the 300s TTL is now a fallback, not the only
  mechanism — ADR-0011's `TermPublished` consumer evicts a cache entry
  immediately on a content update, typically bounding staleness to
  seconds instead of minutes.

### Not built: gRPC health check feeding `/ready`

The original increment plan proposed wiring content-service's
`grpc_health.v1.HealthService` into game-service's `/ready`, so a dead
content-service would show as degraded readiness rather than surfacing
only as per-request `AioRpcError` logs. **Not implemented** — logging on
RPC failure was judged sufficient signal for now; this is the honest gap,
not a finished feature. See "When I would change this."

## Consequences

### Positive

- A schema-checked internal contract instead of two hand-maintained REST
  DTOs drifting apart.
- The cache + fallback pair means a `content-service` blip degrades
  grading (stale term data, bounded by TTL or Kafka invalidation) instead
  of failing it outright, for any term already looked up once.
- Same `TermRepository` port as before — swapping the adapter required no
  application-layer change, proving the boundary was drawn in the right
  place.

### Negative

- **No gRPC health check in `/ready`.** An operator sees content-service
  outages only through request-path warning logs, not a readiness signal
  — worse observability than the plan intended.
- **Random has no fallback.** If content-service is down and no term has
  ever been cached, a new round genuinely cannot start. This is treated
  as correct (there's no stale "random" to fall back to) but is a hard
  failure mode worth naming.
- **Cache is per-process, per-instance.** Running multiple `game-service`
  replicas means each holds its own cache; ADR-0011 already notes this as
  the reason a Redis-backed cache is the natural next step if horizontal
  scaling is added.

## When I Would Change This

- **Wire the gRPC health check into `/ready`** if this ever needs to alert
  an operator before a player notices grading degrading — currently only
  discoverable via logs.
- **Move the cache to Redis** the moment `game-service` runs more than one
  replica — a per-process dict cache silently under-serves cache hits
  across instances, and ADR-0011's Kafka invalidation would need to target
  a shared store instead of one process's memory.
- **Add a gRPC interceptor for retries/circuit-breaking** if content-service
  outages become frequent enough that "log and return None/stale" stops
  being adequate — not justified by observed behavior today.
