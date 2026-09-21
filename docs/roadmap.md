# Product Roadmap

Short PRDs for what's actually shipped, one per phase, product-first — not the
skill-coverage ladder (`skills-map.md`) or the reasoning behind each choice
(`docs/adr/`). This is the doc to read to answer "what does the product do
today and why does that feature exist," in order.

Each entry: the problem, the decision, what shipped. Player-facing behavior
is authoritative in [game-rules.md](./game-rules.md) — this doc points there
instead of restating it.

## Product vs. skills-practice

Two things are true about this repo at once, and conflating them is exactly
what produced overlapping plan files with no roadmap: **Term Rush is a real
product idea** (grade understanding, not string equality; schedule review
with spaced repetition) **and a vehicle for practicing job-market skills**
(microservices, event logs, IaC, Kubernetes) that the product's actual
problem size doesn't demand on its own — see
[ADR-0001](./adr/0001-record-architecture-decisions.md).

Every phase below is tagged:

- **Product** — the game genuinely needed this to be a better learning tool.
  Would exist even at a much smaller portfolio scope.
- **Skills-practice** — the game works without it; it's here because the
  job hunt needs the skill demonstrated somewhere, and this product is the
  vehicle. `skills-map.md` is the ledger for *this* axis — every
  skills-practice phase has a row there.

A phase can be both. Tag reflects the primary reason it exists, not every
side effect.

---

## Phase 1 — Deterministic grading core

**Tag:** Product. This *is* the second goal from the project brief — grade
understanding, not string equality.

**Problem:** the original prototype graded answers with a single 6-line
string-similarity check. `"Unit of Work"` and a correct explanation of what a
UoW *is* scored identically — recognizing an acronym and understanding it
were treated as the same skill.

**Decision:** grade on a 4-slice rubric (Expansion 30 / Concept 40 / Purpose
20 / Example 10), reached through a deterministic chain — exact match, known
alias, fuzzy similarity — before any LLM is involved. Domain stays
framework-free (Clean Architecture, `import-linter`-enforced).

**Shipped:** `Term`/`Session` entities, grader chain, rubric scoring, `POST
/sessions/{id}/answers/submit`. PostgreSQL via SQLAlchemy 2 + Alembic,
12-factor migration process separate from API bootstrap. React client
(Vite + TS + Tailwind) covering the core submit/grade loop.

**Rules:** [game-rules.md § Scoring, § Verdicts](./game-rules.md#scoring)

**ADRs:** [0002](./adr/0002-grading-strategy-and-the-rubric.md) (rubric vs.
string equality), [0003](./adr/0003-principles-before-frameworks.md)
(domain framework-free), [0004](./adr/0004-self-referential-term-bank.md)
(term bank mined from this repo), [0006](./adr/0006-one-image-for-all-services.md)
(one image, one service), [0008](./adr/0008-decoupled-migrations.md)
(migrations decoupled from API bootstrap)

---

## Phase 2 — LLM grading escalation

**Tag:** Product, with a skills-practice edge. A rubric that can't tell
"phrased differently" from "wrong" is a real product ceiling — LLM grading
raises it. The prompt-injection defense (ADR-0013) is the skills-practice
part: a small grading app doesn't strictly need documented adversarial
hardening, but a trust boundary at a public API is exactly where you'd want
to show you take it seriously.

**Problem:** the deterministic chain can't tell "knows the concept, phrased
it differently" from "doesn't know it" — both land as a fuzzy-match Partial.
Widening the fuzzy threshold to catch one makes it catch the other too.

**Decision:** escalate to an LLM judge only on a Partial deterministic
verdict, opt-in per request. The player's free-text answer is untrusted
input reaching a prompt — that's a trust boundary, defended explicitly, not
assumed safe because it's "just a grading app."

**Shipped:** `AnthropicJudgePort`, structured rubric output, `POST
/sessions/{id}/answers/submit/stream` (SSE: live rationale, then one
`graded` event). LLM failure or missing `ANTHROPIC_API_KEY` falls back to
the deterministic score silently — grading never blocks on the LLM path.
Profanity-flagging grader runs before anything else.

**Rules:** [game-rules.md § Getting AI feedback](./game-rules.md#getting-ai-feedback)

**ADRs:** [0013](./adr/0013-prompt-injection-defense-for-llm-grading.md)
(delimiter-escaping, instruction hierarchy, output clamping)

---

## Phase 3a — Microservices split (content-service)

**Tag:** Skills-practice. Nothing about grading answers or scheduling review
requires two services — one Postgres table for terms serves the product
fine at this scale. This split exists to demonstrate service boundaries,
gRPC, and machine-enforced isolation for the job hunt. See
[skills-map.md § API design](./skills-map.md#api-design-rest--grpc--graphql).

**Problem:** term knowledge and game/grading logic were one service sharing
one database. `Term`'s own docstring already stated the intent ("terms are
replaced by content-service publishing a new version, never mutated in
place by the game") before the split existed to make it true.

**Decision:** split term ownership into `content-service`, its own Postgres.
`game-service` no longer has a local `terms` table. Reintroduce per-service
namespaces (`game_service`, `content_service`) so import-linter can enforce
real isolation — resolving ADR-0007's deferred choice.

**Shipped:** `services/content/` (Clean Architecture layers, own DB, REST +
gRPC), `services/game/` calls it over gRPC via `GrpcTermRepository`
(bounded TTL cache, stale-cache fallback on RPC failure). Machine-enforced
forbidden-imports contract in both directions.

**ADRs:** [0007](./adr/0007-flat-service-layout.md) (namespace resolution,
Resolution section), [0009](./adr/0009-grpc-term-lookup.md) (gRPC choice,
cache/fallback design, the gRPC-health-into-`/ready` gap that wasn't built)

---

## Phase 3b — Kafka event log

**Tag:** Skills-practice, though it earns a small product win (cache
staleness bounded by an event instead of only a TTL). See
[skills-map.md § Distributed systems](./skills-map.md#distributed-systems-queues-caching-consistency).

**Problem:** `game-service`'s gRPC term cache relied on a flat 300s TTL
alone — a term edited in `content-service` could read stale for up to 5
minutes. Separately, `game-service` grading an answer is a fact other
consumers (future analytics) will eventually want, with no synchronous
caller waiting on it.

**Decision:** a Kafka-API event log (Redpanda locally), not a queue —
replayability is the one honest reason to prefer a log here. Producer never
blocks the request it's a side effect of; consumer runs in-process (not a
separate container — the cache it invalidates is that process's own dict).

**Shipped:** `content-service` publishes `TermPublished`, consumed by
`game-service` to evict the matching gRPC cache entry immediately.
`game-service` publishes `AnswerGraded`. Consumer self-heals via a
supervised restart loop with backoff; `/ready` degrades (not fails) when
either consumer goes stale.

**Update (2026-09-21):** `AnswerGraded` gained its first consumer — a
per-term verdict tally (`term_stats` table), surfaced via `GET
/terms/{id}/stats` as an observed-difficulty ratio. This is the small,
warehouse-free version of [ADR-0005](./adr/0005-data-engineering-scope.md)'s
`mart_term_difficulty` idea (see "Not yet started" below) — the game's own
play data recalibrating the game, without Dagster/dbt.

**ADRs:** [0011](./adr/0011-kafka-event-log.md) (event catalog, at-most-once
delivery accepted and why, consumer supervision, `/ready` degradation)

---

## Not yet started

- **GraphQL BFF** — collapse the session screen's 3 REST round-trips into
  one query + one mutation. Scoped, not built. See
  [README § Next Steps](../README.md#next-steps).
- **Phase 4 (cloud deploy)**, **Phase 5 (scaling narrative)** — see README;
  no ADRs yet because no decisions have been made yet.

---

## How this doc stays honest

A phase only gets an entry here once it's shipped and verified, mirroring
`skills-map.md`'s rule: this describes what exists, not what's intended.
When a new phase lands, add one entry above "Not yet started," cite the
ADR(s) that defend it, and link the `game-rules.md` section if it changed
player-facing behavior. If a decision later gets superseded (like
ADR-0007's namespace reversal), the phase entry stays as shipped-then, not
rewritten — the ADR's own Resolution/Status field is where the correction
lives.
