# ADR-0011: Kafka Event Log for Cross-Service Notifications

- **Status:** Accepted
- **Date:** 2026-09-21
- **Relates to:** ADR-0009 (gRPC term lookup), ADR-0007 (service isolation)

## Context

`game-service` caches term data it reads from `content-service` over gRPC
(`GrpcTermRepository`, ADR-0009) — content-service's writes are otherwise
invisible to it. Before this ADR, that cache relied on a flat 300-second
TTL alone: a term edited via `content-service`'s authoring endpoint could
read stale in `game-service` for up to 5 minutes.

Two services also want to react to each other's state changes without a
direct call: `game-service` grading an answer is an event other consumers
(future: analytics, leaderboard) care about; `content-service` publishing
a term is an event `game-service`'s cache cares about. Both are
notifications, not requests — the producer doesn't need or want a
synchronous response.

Redpanda is used locally instead of vanilla Kafka + Zookeeper: Kafka-API-
compatible, single binary, no separate coordination service to run in
Compose. `confluentinc/cp-kafka` in KRaft mode is a one-image swap if
"real Kafka" specifically matters to a reviewer — nothing in the code
depends on Redpanda specifically (`aiokafka` speaks the Kafka wire
protocol, not a Redpanda-specific API).

## Decision

A Kafka-API event log carries two event types today:

- `AnswerGraded` (topic `answers.graded`) — published by `game-service` on
  every graded answer. No consumer yet; exists for future analytics/
  leaderboard projections. Replayability is the reason this is a log and
  not a simple queue: a new consumer can be added later and read the full
  history, not just events from its start time.
- `TermPublished` (topic `terms.published`) — published by `content-service`
  on every term write. Consumed by `game-service` to evict the matching
  entry from `GrpcTermRepository`'s cache immediately, rather than waiting
  out the TTL.

Both topics carry `termrush_core.events.EventEnvelope` (`libs/core`) as
JSON: `event_id`, `event_type`, `payload: dict`, `occurred_at`,
`schema_version`. A plain dict payload, not a typed per-event schema —
this proves the publish/consume mechanics first; a schema registry is a
later concern if the event catalog outgrows two event types.

### Producer: fire-and-forget, never blocks the request

`KafkaEventPublisher.publish()` awaits `send_and_wait` (waits for the
broker's ack, so not a true fire-and-forget on the wire) but catches
`KafkaError` and logs rather than propagating. A broker outage must not
fail the request that triggered the event — grading an answer or
publishing a term is the caller's actual intent; the event is a side
effect. Verified live: stopping the Redpanda container mid-session, a
`POST /answers/submit` still returned 200.

**Delivery semantics: at-most-once from the producer's perspective.** A
crash between the domain write committing and `publish()` being called —
or a broker error caught and swallowed as above — loses that one event
permanently. Accepted here because:

- `AnswerGraded` has no consumer yet; a lost event costs nothing today.
- `TermPublished`'s only consumer (cache invalidation) has the 300s TTL as
  a correctness backstop — a lost event means the cache serves a stale
  term for at most 5 more minutes, not forever.

An outbox pattern (write the event in the same transaction as the domain
change, a separate relay publishes it) would close this gap and give
at-least-once delivery instead. Deliberately not built yet — see "When I
would change this."

### Consumer: in-process, not a separate process

`game-service` runs the `TermPublished` consumer as a background
`asyncio.Task` inside its own API process, started via FastAPI's
`lifespan`, not as a separate `game-consumer` container. This was a
correction mid-implementation: the obvious design (a second container,
matching how consumer processes are usually described) has a real bug —
the cache to invalidate is a plain Python dict on the specific
`GrpcTermRepository` instance request handlers read from. A second
process gets its own interpreter, its own heap, its own empty cache; a
separate `game-consumer` would invalidate a cache nothing had ever
populated, silently doing nothing.

**The general rule this surfaced:** two processes cannot share in-memory
state without an explicit external mechanism (a shared store, IPC).
Sharing the actual dict requires sharing the process. The alternative
that *would* let this be a separate process is moving the cache into
Redis (already in the stack, unused today — see "When I would change
this").

**Consumer resilience:** `aiokafka`'s own client retries connection/broker
errors internally without raising into application code (observed live:
stopping Redpanda produced continuous internal reconnect-attempt logs,
not a crashed consumer). The remaining risk is an *unexpected* exception —
a bug, an unhandled error type — killing the loop outright. A bare
`_supervise` wrapper catches any exception from `consume_term_published`,
logs it with a traceback, and restarts after a 5-second backoff,
indefinitely, until the task is cancelled by lifespan shutdown. Without
this, that failure mode is silent and permanent: `TermPublished` stops
being consumed for the rest of the process's life, degrading to
TTL-only with nothing surfacing it.

**Idempotency:** re-delivery of the same `TermPublished` message (Kafka's
consumer-side guarantee is at-least-once, not exactly-once) is harmless —
`GrpcTermRepository.invalidate()` evicting an already-evicted or
never-cached `term_id` is a no-op. No dedup logic needed for this
specific consumer; worth stating explicitly since idempotent consumption
is a real Kafka Term Rush vocabulary word `content-service`'s own domain
would need to define if the event catalog ever grows.

### Readiness: consumer health degrades `/ready`, never fails it

`ConsumerHealth` tracks the timestamp of the consumer loop's last
confirmed-alive moment (start of every attempt and every message
received). `/ready` reports `{"status": "degraded", "reason":
"term_cache_invalidator_stale"}` once that timestamp is more than 60
seconds old — long enough that `_supervise`'s 5-second backoff has
plausibly failed to recover, not just backed off once. This never returns
a non-200 or otherwise gates traffic: a dead consumer means cache
invalidation has degraded to TTL-only, which is a real but survivable
degradation, not an outage.

### Optional dependency, same pattern as `ANTHROPIC_API_KEY`

`KAFKA_BROKER_URL` unset on either service: no producer constructed
(`EventPublisher` falls back to the existing in-memory no-op), no
consumer started, `/ready` has nothing to check. Tests and any deployment
without Kafka configured are unaffected — this mirrors how
`ANTHROPIC_API_KEY` unset already disables the LLM grading path without
breaking anything else.

## Consequences

### Positive

- Cache staleness bounded by an event, not just a flat TTL — typical
  staleness window drops to however long the consumer takes to process
  the message (observed: ~2s), not up to 300s.
- A request-failing dependency (Kafka down) cannot fail a request that
  doesn't actually need Kafka to succeed.
- An unexpected consumer crash self-heals instead of silently degrading
  forever with no signal.
- `/ready` gives an operator something to alert on before a player
  notices stale content, without false-alarming on a transient blip.

### Negative

- At-most-once producer delivery: an event can be silently lost. Accepted
  for both current event types (see above); would need revisiting before
  a consumer that requires stronger guarantees is added.
- No schema registry: `payload: dict` has no compile-time or runtime
  contract beyond what each consumer chooses to read defensively (the
  invalidator's `try/except (json.JSONDecodeError, KeyError)` around
  `payload["term_id"]` is that defense today).
- `AnswerGraded` has no consumer — it's provisioned capability, not yet
  load-bearing. Worth being explicit that this is true, since an unused
  topic is easy to mistake for a finished feature.

## When I Would Change This

- **Outbox pattern**: if a lost `TermPublished` event ever mattered more
  than "stale for up to 5 minutes" — e.g. if a future consumer's
  correctness (not just freshness) depended on seeing every event — move
  the publish into the same transaction as the domain write via an
  outbox table, with a separate relay process doing the actual Kafka
  send. This is real added infrastructure, not a config flag; not
  justified by today's two event types.
- **Redis-backed term cache**: if the term cache invalidator ever needs to
  run as a genuinely separate process (e.g. horizontal scaling means
  multiple `game-service` instances each need their own consumer, but
  invalidation needs to hit every instance's cache) — move
  `GrpcTermRepository`'s cache into Redis, which is already provisioned in
  this stack but unused. That turns "share the process" into "share the
  store," and a separate consumer process becomes correct again.
- **Schema registry / typed events**: once the event catalog grows past a
  handful of types, or a second team/service starts consuming these
  topics, replace `payload: dict` with per-event Pydantic schemas (or
  Avro/Protobuf if cross-language consumers appear) — `payload: dict`
  was always meant to prove the mechanics first.
- **`confluentinc/cp-kafka` (KRaft)**: swap for Redpanda if a reviewer
  specifically needs to see vanilla Kafka rather than a compatible
  implementation. One `compose.yml` image change; `aiokafka` doesn't care.
