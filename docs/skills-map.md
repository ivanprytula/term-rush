# Skills Map

The honest scoreboard. Every ladder point, where it lives in the codebase, and what
state it is actually in — not what I intend it to be.

**This is the skills-practice ledger, not the product spec.** Term Rush is two
things at once: a real product idea (grade understanding, schedule review — see
[README](../README.md)) and a vehicle for demonstrating job-market skills the
product's actual problem size doesn't demand on its own (ADR-0001). This file
tracks the second axis. [`docs/roadmap.md`](./roadmap.md) tracks the first —
each shipped phase there is tagged **Product** or **Skills-practice** so it's
never ambiguous which reason a given piece of infrastructure exists for. A row
here with no product need is not a smell; it's the point — see "Deliberate
omissions" below for the mirror case (skills deliberately *not* practiced).

**Status vocabulary:**

| Status | Meaning |
| --- | --- |
| ✅ **Covered** | Implemented, tested, and load-bearing. A reviewer can read real code. |
| 🟡 **Partial** | Exists but shallow, or covered in one place where it should be several. |
| ⏳ **Planned** | Scheduled in a named phase. Not started. |
| ⏸️ **Deferred** | Deliberately postponed. Reason recorded. |
| ❌ **Skipped** | Decided against. Reason recorded — this is a *decision*, not a gap. |

Nothing here is a checkbox for its own sake. Where a skill has no honest job in this
product, it is marked ❌ with the reasoning, because a defended "no" is better signal
than a contrived "yes".

ADR numbers below past ADR-0007 (see `docs/adr/`) are reserved for decisions not yet
written — the number is fixed so cross-references here don't drift, but the ADR itself
doesn't exist until the linked phase starts.

---

## Horizontal bar — breadth

### API design (REST / gRPC / GraphQL)

| Facet | Status | Where |
| --- | --- | --- |
| REST, domain-language endpoints | ✅ P1 | `api/routers/` — `POST /game-rounds/{id}/answers/submit`, never `/api/process` |
| OpenAPI → generated TS client | ✅ P1 | `just generate-client`; CI's `web-build` job regenerates from the live schema and runs `tsc -b` — API drift fails the build |
| gRPC | ✅ P3 | `game-service` → `content-service` term lookup. Chosen for this hop specifically: high-frequency, internal, schema-first, latency-sensitive — the case where gRPC beats REST rather than merely differs from it. ADR-0009. |
| GraphQL BFF | ⏳ P3 | Strawberry. One query replacing 3 REST round-trips for the session screen — measured, not asserted. ADR-0010. |

**The point to make in an interview:** three protocols, three *reasons*. REST for the
public API, gRPC for the internal hot path, GraphQL for the client aggregation problem.
Using all three without being able to say why each is where it is would be worse than
using one.

### Frontend to TypeScript + React level

| Facet | Status | Where |
| --- | --- | --- |
| React 19 + TS strict | ⏳ P1 | `apps/web/` |
| Real-time game loop | ⏳ P1 | `useGameLoop.ts` — rAF, not CSS keyframes, because Survival needs runtime-variable acceleration |
| Server state vs client state | ⏳ P1 | TanStack Query (server) + Zustand (game loop). The distinction is the skill. |
| Streaming UI | ⏳ P2 | SSE consumption for live rubric grading + interim voice transcripts |
| Accessibility | ⏳ P1 | Keyboard-playable without mouse; reduced-motion honored; ARIA live regions for score |

### SQL + data modeling, one NoSQL store

| Facet | Status | Where |
| --- | --- | --- |
| Relational modeling | ⏳ P1 | Postgres: sessions, answers, FSRS card states. Normalized, FK-constrained, indexed on real query patterns. |
| Term selection strategy | ⏳ Planned | Weakness-driven priority scoring (spaced repetition, FSRS-style) — not started. Today `GetRandomTerm` is session-scoped exclusion only, not weakness-scored. |
| Migrations | ⏳ P1 | Alembic, expand-contract for anything destructive |
| NoSQL | ⏸️ Deferred | Plan was MongoDB for term knowledge objects (deeply nested, variable-shaped, read-heavy — a real document fit). content-service shipped on Postgres instead (JSON column) when the split landed — simpler, one less datastore to operate, and the access pattern turned out not to need document flexibility yet. Revisit if term objects grow genuinely variable-shaped. |
| Vector store | ⏳ P3 | pgvector for semantic term similarity + RAG retrieval. Deliberately *not* a separate vector DB — see ADR-0012. |
| Query performance | ⏳ P4 | `EXPLAIN ANALYZE` on the leaderboard and review-queue queries, documented before/after |

### CI/CD, containers, secrets, DNS/HTTPS

| Facet | Status | Where |
| --- | --- | --- |
| Containers | ✅ P1 | Multi-stage `services/game/Dockerfile`, non-root `USER app`, `curl`-based healthcheck. Pinned base digests still open — tag only today. |
| Compose (daily driver) | ✅ P1 | `just up` / `just run-all`; healthchecks on postgres, game, content. No observability-stack profile to skip yet — nothing to skip until P2 ships it. |
| CI pipeline | 🟡 P1 | `.github/workflows/ci.yml`: ruff, ty, import-linter, pytest. No frontend test job yet — Playwright (`just web-test-ui`) runs locally only, and there's no vitest (no frontend unit-test framework). |
| Secrets management | ⏳ P1 | `.env.example` only in git; Secret Manager in cloud; **no secrets as CLI args** |
| DNS / HTTPS / TLS | ⏳ P4 | Managed cert on Cloud Run, custom domain, HSTS. The 80/20. |
| Kubernetes | ⏳ P1→P4 | Helm + kind from P1, cloud overlays in P4. See ADR-0015 (kind over k3s/minikube). |

### Security: authN/authZ, OWASP, secrets

| Facet | Status | Where |
| --- | --- | --- |
| AuthN | ⏳ P1 | JWT access + refresh rotation, argon2id hashing. Written by hand *once* to show I understand it, then noted where I'd swap in a managed IdP. ADR-0014. |
| AuthZ | ⏳ P1 | Resource ownership checks — a player cannot read another player's review queue. The boring one people skip. |
| OWASP Top 10 | ⏳ P1 | `docs/security.md` walks all 10 against *this* codebase with the specific mitigation and the file it lives in. Not a generic checklist. |
| Rate limiting | ⏳ P1 | Redis sliding window on auth + grading endpoints |
| Dependency scanning | ⏳ P1 | `pip-audit` + `npm audit` in CI, failing the build |
| Input validation at trust boundaries | ⏳ P1 | Pydantic at every edge; length caps on free-text answers before they reach an LLM prompt |
| Prompt injection defense | ✅ Covered | Player answers are untrusted input flowing into an LLM. Structured tool-use output, delimiter-escaped, instruction-hierarchy'd, output-clamped. `infrastructure/llm_judge.py`, ADR-0013 — this is the security topic most AI portfolio projects ignore entirely. No adversarial classifier yet; scope and reversal condition recorded in the ADR. |

### Observability: logs, metrics, traces

| Facet | Status | Where |
| --- | --- | --- |
| Structured logging | ✅ P1 | `infrastructure/logging.py` — JSON formatter, OTel trace/span injection, redacted-fields set (answer, password, token, secret, ...) |
| Metrics | ⏳ P2 | Prometheus: RED on HTTP, grading latency by `matched_via`, LLM cost per session |
| Traces | ⏳ P2 | OTel across api → celery → llm. The multi-hop trace is the demo. |
| Dashboards + alerts | ⏳ P4 | Grafana, with SLOs that have error budgets rather than vibes |

---

## Vertical bar — backend depth (the differentiator)

### Async Python and concurrency models

| Facet | Status | Where |
| --- | --- | --- |
| async/await end-to-end | ⏳ P1 | FastAPI + SQLAlchemy 2.0 async + asyncpg. No sync driver hiding in a thread pool. |
| Structured concurrency | ⏳ P2 | `asyncio.TaskGroup` for fan-out (grading several answers, parallel retrieval) |
| Backpressure + bounded concurrency | ⏳ P2 | Semaphore-bounded LLM calls; the unbounded-`gather` bug, avoided on purpose and documented |
| CPU-bound vs IO-bound | ⏳ P2 | FSRS batch recompute is CPU-bound → process pool, not the event loop. Knowing *which* is the skill. |
| Cancellation + timeouts | ⏳ P2 | `asyncio.timeout`, correct `CancelledError` propagation |
| **Demonstration piece** | ⏳ P2 | `docs/async-python.md` — a benchmark showing sync vs async vs bounded-async under load, with the numbers and the explanation of *why* |

### Distributed systems: queues, caching, consistency

| Facet | Status | Where |
| --- | --- | --- |
| Task queue | ⏳ P2 | Celery + RabbitMQ. Broker's actual job. |
| Event log | ✅ P3 | Kafka (Redpanda locally). Chosen for **replayability**, which is the only honest reason to prefer it over a queue. `game-service` publishes `AnswerGraded`; `content-service` publishes `TermPublished`, consumed in-process by `game-service` to invalidate its gRPC term cache. Verified E2E: a term update evicts the stale cache entry, next lookup refetches over gRPC. ADR-0011. |
| Caching | ⏳ P1→P2 | Redis: leaderboard ZSET (native fit), LLM grade cache, rate limiter. Three distinct uses. |
| Cache invalidation | ⏳ P2 | The hard one. Documented strategy per cache, including the stale-read window we accept. |
| Consistency trade-offs | ⏳ P3 | Leaderboard is eventually consistent; session state is not. Documented with the reasoning. |
| Reliable messaging | ⏳ P3 | Transactional outbox, idempotent consumers, DLQ. Proven by a chaos test: kill a consumer mid-stream, restart, assert exactly-once effect. |
| Failure modes | ⏳ P2 | Circuit breaker on the LLM, graceful degradation to deterministic grading, documented fallback matrix |

### System design at scale

| Facet | Status | Where |
| --- | --- | --- |
| Written design docs | ⏳ P5 | `docs/architecture.md`, C4 context → container → component |
| Scaling narrative | ⏳ P5 | `docs/scaling.md` — "here is the system at 100 users, at 100k, at 10M; here is what breaks first at each step and what I'd do". The single most interview-relevant document in the repo. |
| Capacity estimation | ⏳ P5 | Back-of-envelope: QPS, storage growth, LLM spend per MAU |
| Load testing | ⏳ P4 | k6 against the real deployment; HPA thresholds derived from the numbers, not guessed |

### Performance profiling and tuning

| Facet | Status | Where |
| --- | --- | --- |
| Python profiling | ⏳ P4 | `py-spy` flamegraph on the grading hot path |
| Query profiling | ⏳ P4 | `EXPLAIN ANALYZE`, index added *after* proving the seq scan hurts |
| Frontend profiling | ⏳ P4 | React Profiler + Lighthouse; game loop must hold 60fps with 20 terms on screen |
| **Method, not anecdote** | ⏳ P4 | `docs/performance.md` — measure → hypothesize → change → re-measure, with at least one honest "I was wrong about the bottleneck" |

---

## Emerging — front-loaded deliberately

### AI orchestration / RAG

| Facet | Status | Where |
| --- | --- | --- |
| LLM as grader, not chatbot | ⏳ P2 | Structured rubric output, validated, with deterministic fallback |
| RAG over the term corpus | ⏳ P3 | Retrieval grounds the judge in the term's real definition, so it grades against *this* corpus rather than the model's memory. `RAG` is also a term in the game bank. |
| Embedding pipeline | ⏳ P3 | Chunk → embed → pgvector → hybrid search (vector + keyword). Reranking. |
| Retrieval evaluation | ⏳ P3 | Recall@k on a labeled set. Most RAG demos never measure retrieval quality; that is the differentiator. |
| Cost + latency control | ⏳ P2 | Caching, budget guard, model tiering (cheap model triages, expensive model only for Boss Rounds) |

### Agentic workflows and tool use (MCP)

| Facet | Status | Where |
| --- | --- | --- |
| MCP server | ⏳ P3 | Term Rush exposes its own term bank + player progress as an MCP server — so Claude Code (or any MCP client) can query it. `MCP` is a term in the game; the game speaks it. |
| Tool-use loop | ⏳ P3 | Content authoring agent: given a new term, it searches, drafts a knowledge object, self-critiques against the schema, submits for review. Real tool calls, not a prompt. |
| Human-in-the-loop | ⏳ P3 | Generated terms land in a review queue. An agent that writes to prod unreviewed is a liability, and saying so is the senior move. |
| Eval harness | ⏳ P3 | Golden set of terms; agent output scored automatically. Prevents prompt-change regressions. |

### Vector databases and embedding pipelines

| Facet | Status | Where |
| --- | --- | --- |
| pgvector | ⏳ P3 | HNSW index, cosine distance |
| **Why not Pinecone/Weaviate/Qdrant** | ❌ | ADR-0012. At this corpus size (~10³ terms) a dedicated vector DB is a second datastore to operate for zero benefit. Knowing when *not* to add infrastructure is the point. The ADR states the corpus size at which I'd switch. |

### Prompt / context engineering as engineering

| Facet | Status | Where |
| --- | --- | --- |
| Versioned prompts | ⏳ P2 | In-repo, reviewed like code, never inline f-strings scattered in handlers |
| Snapshot tests | ⏳ P2 | Prompt changes produce a reviewable diff of model output on a fixed input set |
| Structured output | ⏳ P2 | Schema-constrained rubric; parse failures are a metric, not an exception swallowed |
| Context budgeting | ⏳ P3 | Explicit token budget per request; retrieval trimmed to fit; measured |
| Injection hardening | ⏳ P2 | See Security. Player free-text reaches a prompt — that is a trust boundary. |

### Fluency with AI coding assistants

| Facet | Status | Where |
| --- | --- | --- |
| Repo is agent-legible | ⏳ P1 | `CLAUDE.md` with architecture invariants, conventions, and the layering rules an agent must not violate |
| Agent-enforceable invariants | ✅ | import-linter contracts — an agent (or human) that breaks the layering fails CI. Machine-checked architecture, not documented hope. |
| Workflow documented | ⏳ P5 | `docs/ai-assisted-development.md` — what I delegate, what I review line-by-line, where agents produced wrong code in *this* project and how it was caught |

---

## Deliberate omissions

| Thing | Why not |
| --- | --- |
| Separate vector DB | ADR-0012 — corpus too small to justify a second datastore |
| Production Kubernetes | ADR-0015 — Cloud Run fits the cost profile; K8s proven on kind instead |
| Applied AWS deploy | Cost. Terraform written and `plan`-clean; the port/adapter boundary is the real demonstration |
| CONTRIBUTING.md | Solo project |
| Microservices beyond two | Two services is enough to show distributed concerns. Three would be theatre. |
| gRPC for the public API | Browsers need grpc-web + a proxy; REST is correct here. gRPC earns its place only on the internal hop. |

---

## How to read this as a reviewer

Fastest path to judging whether I can actually do this work:

1. `docs/adr/` — the decisions, especially the negative ones
2. `docs/scaling.md` — the system design thinking (P5)
3. `services/game/game_service/domain/` — the code with no framework in it
4. `docs/performance.md` — whether I measure or guess (P4)
5. This file — whether I am honest about gaps
