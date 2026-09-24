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

**Depth tracking:**

Each ✅ row also has a *Depth* column tracking maturity of the implementation:

| Depth | Meaning |
| --- | --- |
| **L1: Breadth** | Feature exists, minimal viable implementation. Proof-of-concept level. |
| **L2: Robustness** | Feature exists with error handling, edge cases covered, tested. Production-ready. |
| **L3: Optimization** | Feature tuned for performance, measured trade-offs, documented. Interview-grade. |
| **L4: Generalization** | Feature abstracted to serve multiple use cases, extensible. Architectural pattern. |

Nothing here is a checkbox for its own sake. Where a skill has no honest job in this
product, it is marked ❌ with the reasoning, because a defended "no" is better signal
than a contrived "yes".

ADR numbers below past ADR-0007 (see `docs/adr/`) are reserved for decisions not yet
written — the number is fixed so cross-references here don't drift, but the ADR itself
doesn't exist until the linked phase starts.

---

## Horizontal bar — breadth

### API design (REST / gRPC / GraphQL)

| Facet | Status | Depth | Where |
| --- | --- | --- | --- |
| REST, domain-language endpoints | ✅ P1 | L2 | `api/routers/` — `POST /game-rounds/{id}/answers/submit`, never `/api/process`. Error handling (404, 422, 500) with structured responses. Tested E2E. Next: status code audit against actual use cases. |
| OpenAPI → generated TS client | ✅ P1 | L2 | `just generate-client`; CI regenerates and runs `tsc -b` — API drift fails the build. Schema-first contract. Next: breaking-change detection in PR workflow. |
| gRPC | ✅ P3 | L2 | `game-service` → `content-service` term lookup. High-frequency, internal, latency-sensitive. Protobuf schema tracked. Next: load testing to prove latency claim. |
| GraphQL BFF | ✅ P3 | L1 | Strawberry, one `sessionScreen` query replacing 2 REST round-trips. `randomTerm` unused (schema mismatch). Next: wire unused fields or remove them; validate N+1 query patterns. |

**The point to make in an interview:** three protocols, three *reasons*. REST for the
public API, gRPC for the internal hot path, GraphQL for the client aggregation problem.
Using all three without being able to say why each is where it is would be worse than
using one.

### Frontend to TypeScript + React level

| Facet | Status | Depth | Where |
| --- | --- | --- | --- |
| React 19 + TS strict | ✅ P1 | L2 | `services/web/src/` — React 19.2.8, TypeScript 6.0.2, Vite SWC. Type-strict, no `any`. ESLint + React hooks linting enforced. Next: add React Profiler traces for frame-rate verification. |
| Real-time game loop | ✅ P1 | L2 | `useSprintCountdown.ts` — `requestAnimationFrame` syncs to `performance.now()`. Re-frames on every tick, stops at zero. Used by Sprint mode. Next: measure 60fps under load; prove no dropped frames. |
| Server state vs client state | ✅ P1 | L2 | Generated OpenAPI client (Axios, typed) for server; React state + refs for UI (theme, voice language, countdown, speech, round lifecycle). No external state lib — component-local is correct. Next: document state ownership matrix. |
| Streaming UI | ✅ P2 | L1 | `submitAnswerStream.ts` — hand-rolled SSE parser. Streams `rationale_delta` from LLM on every token. Boss Round uses this. Next: add reconnection logic on network fail; handle mid-stream response timeout. |
| Accessibility | ✅ P1 | L2 | Keyboard playable (aria-label, autofocus, Enter submit). ARIA: live regions for score, alerts for verdicts. Speech input + language toggle. Playwright tests verify keyboard-only. Next: axe-core audit; reduce-motion testing. |

### SQL + data modeling, one NoSQL store

| Facet | Status | Where |
| --- | --- | --- |
| Relational modeling | ✅ P1 | Postgres: `game_rounds` (JSON blob + denormalized `total_score`, `mode` for leaderboard sorts), `term_stats` (columnar verdict tally by term), `content_service.terms` (relational 8-table schema for expansion/validation/sources). FK-constrained, indexed on real query patterns. ADR-0005 justifies JSON for rounds. |
| Term selection strategy | ⏳ Planned | Weakness-driven priority scoring (spaced repetition, FSRS-style) — not started. Today `GetRandomTerm` is session-scoped exclusion only, not weakness-scored. |
| Migrations | ✅ P1 | Alembic: 8 migrations tracked (initial → add term stats → drop terms → add mode denormalization → add total_score denormalization). Expand-contract pattern for destructive changes. |
| NoSQL | ⏸️ Deferred | Plan was MongoDB for term knowledge objects. content-service shipped on Postgres instead (JSON column) when the split landed — simpler, one less datastore to operate. Access pattern turned out not to need document flexibility yet. ADR-0005 states corpus-size reversal point. |
| Vector store | ⏳ P3 | pgvector for semantic term similarity + RAG retrieval. Deliberately *not* a separate vector DB — see ADR-0012. |
| Query performance | ⏳ P4 | `EXPLAIN ANALYZE` on leaderboard queries (multi-mode aggregation, session sum). Indexed by mode + total_score for sort efficiency. |

### CI/CD, containers, secrets, DNS/HTTPS

| Facet | Status | Where |
| --- | --- | --- |
| Containers | ✅ P1 | Multi-stage `services/game/Dockerfile` (Python 3.14 slim, builder stage, non-root `USER app`). Healthcheck + image scan ready. Web service + compose stacks verified (docker compose up). |
| Compose (daily driver) | ✅ P1 | `compose.yml` unified: game-service, content-service, postgres, redis. Health checks on all. Two Justfile recipes: `just dev` (hot-reload) and containerized variant. Gateway proxies `/graphql`, `/game-rounds/...` to game; `/api/terms/...` to content. |
| CI pipeline | 🟡 P1 | `.github/workflows/ci.yml`: `uv sync` → `just precommit` (ruff, ty, import-linter) → pytest. No frontend test job yet — Playwright tests (`just web-test-ui`) run locally only; CI comment documents this gap. |
| Secrets management | ✅ P1 | `.env.example` tracked (safe schema); `.env` gitignored. No secrets in code, args, or env vars. ANTHROPIC_API_KEY pulled from env at runtime only. |
| DNS / HTTPS / TLS | ⏳ P4 | Managed cert on Cloud Run, custom domain, HSTS. The 80/20. |
| Kubernetes | ⏳ P1→P4 | Helm + kind from P1, cloud overlays in P4. See ADR-0015 (kind over k3s/minikube). |

### Security: authN/authZ, OWASP, secrets

| Facet | Status | Where |
| --- | --- | --- |
| AuthN | ⏳ P1 | JWT access + refresh rotation, argon2id hashing. Hand-implemented once to show competency, then noted where I'd use a managed IdP. ADR-0014. Not yet implemented in game-service. |
| AuthZ | 🟡 P1 | Resource checks: a player's answers and leaderboard rank are their own (implicit via session ownership). Review queue checks added but not wired to API yet. ADR-0014 defers full RBAC. |
| OWASP Top 10 | ⏳ P1 | Security posture documented; specific mitigations in code (see Prompt injection, Input validation below). Full OWASP walkthrough deferred to P3. |
| Rate limiting | ⏳ P1 | Redis sliding window on auth endpoints (not yet implemented). Grading endpoint has answer-length cap (512 chars) instead. |
| Dependency scanning | ⏳ P1 | `pip-audit` + `npm audit` as pre-commit hooks; not yet wired to CI fail gates. |
| Input validation at trust boundaries | ✅ P1 | Pydantic schemas on all API endpoints. Answer length capped at 512 chars (game rule + LLM input safety). Term ID validated (1-64 chars, alphanumeric). `api/schemas.py`. |
| Prompt injection defense | ✅ Covered | Player answers (untrusted input) flow to Claude with JSON escaping, instruction hierarchy, output schema validation. Structured rubric output prevents injection via response. `infrastructure/llm_judge.py`, ADR-0013. No adversarial classifier; scope recorded. |

### Observability: logs, metrics, traces

| Facet | Status | Where |
| --- | --- | --- |
| Structured logging | ✅ P1 | `infrastructure/logging.py` — JSON formatter (Uvicorn + stdlib), OTel trace/span injection (trace_id, span_id on every log), redacted-fields set (answer, password, token, api_key). Verified in docker logs. |
| Metrics | ⏳ P2 | Prometheus client imported; not yet wired. Plan: RED on HTTP (request rate / errors / duration), grading latency by `matched_via`, LLM cost per session. |
| Traces | ⏳ P2 | OTel imported; propagation headers prepared. Full E2E trace (HTTP → gRPC → Kafka → stats endpoint) deferred. |
| Dashboards + alerts | ⏳ P4 | Grafana queried against Prometheus. SLOs with error budgets (not guesses). Deferred to post-P1. |

---

## Vertical bar — backend depth (the differentiator)

### Async Python and concurrency models

| Facet | Status | Depth | Where |
| --- | --- | --- | --- |
| async/await end-to-end | ✅ P1 | L2 | FastAPI async handlers + SQLAlchemy 2.0 async ORM + asyncpg driver. No sync code blocking the loop. `app.py` lifespan uses `async with` for startup/shutdown. All I/O (DB, gRPC, Kafka) is async-native. Next: audit event-loop blocking (call `loop.slow_callback_duration`). |
| Structured concurrency | 🟡 P2 | L1 | `AIOKafkaConsumer` + `asyncio.create_task()` for 2 concurrent listeners (term-stats, cache invalidation). No `TaskGroup` yet. Next: migrate to `TaskGroup` for cancellation guarantees; add timeout + exception handling. |
| Backpressure + bounded concurrency | ⏳ P2 | L0 | Not implemented. LLM calls are sequential (1 per grade). Next: add `asyncio.Semaphore` to bound concurrent calls; measure queue depth under load. |
| CPU-bound vs IO-bound | ⏳ P2 | L0 | FSRS batch recompute not yet implemented (P3+). Next: benchmark CPU work on event loop vs `ProcessPoolExecutor`; document the decision. |
| Cancellation + timeouts | ⏳ P2 | L0 | Not implemented. Next: add `asyncio.timeout()` to LLM calls + proper `CancelledError` propagation. |
| **Demonstration piece** | ⏳ P2 | L0 | `docs/async-python.md` — benchmark showing sync vs async under load. Deferred until concurrency patterns mature (P2→P3). |

### Distributed systems: queues, caching, consistency

| Facet | Status | Where |
| --- | --- | --- |
| Task queue | ⏳ P2 | Celery + RabbitMQ. Broker's actual job. Deferred — sequential grading sufficient for early players. |
| Event log | ✅ P3 | Kafka (Redpanda in compose). `game-service` publishes `AnswerGraded`, consumed in-process to tally per-term verdict counts (`GET /terms/{id}/stats`). `content-service` publishes `TermPublished`, consumed by `game-service` to invalidate its gRPC term cache. Verified E2E: term update evicts cache, graded answer appears in stats within seconds. `infrastructure/kafka_event_publisher.py`, ADR-0011. |
| Caching | ⏳ P1→P2 | Redis configured (`REDIS_URL`) but not yet wired. Plan: LLM grade cache (key=hash(term_id, answer)), rate limiter (sliding window on auth). Leaderboard uses Postgres directly (denormalized total_score, mode fields for efficient sorting — no cache needed). |
| Cache invalidation | ⏳ P2 | Not yet implemented (Redis configured but unused). Plan: grade cache TTL (identical answers use cached grade). Term cache invalidated on `TermPublished` event (for gRPC term lookups). ADR-0011 documents the topology. |
| Consistency trade-offs | ✅ P3 | Leaderboard is eventually consistent (cache + event-driven invalidation). Session state (game rounds, answers) is immediate on write (no cache). ADR-0011 documents both. |
| Reliable messaging | ⏳ P3 | Kafka provides replayability; idempotent consumers not yet implemented (in-memory dedup sufficient at current scale). Transactional outbox deferred. |
| Failure modes | ✅ P2 | LLM grading fails gracefully: returns deterministic verdict on timeout or API error, logged + counted. No cascading failure — answer always grades via exact/alias/fuzzy path. `llm_judge.py`. |

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
| LLM as grader, not chatbot | ✅ P2 | Structured `ClaudeRubricOutput` Pydantic model. Claude grades Boss Round answers against term expansion, returns typed rubric + feedback. Fails gracefully to deterministic grading if Claude times out or errors. `infrastructure/llm_judge.py`. |
| RAG over the term corpus | ⏳ P3 | Not yet implemented. Plan: embed term definitions, hybrid search (vector + keyword match) to retrieve context, pass to Claude with the player's answer for grading. Would ground Claude in corpus instead of model's memory. |
| Embedding pipeline | ⏳ P3 | Chunk → embed → pgvector → hybrid search. Deferred. pgvector extension installed but unused. |
| Retrieval evaluation | ⏳ P3 | Recall@k on labeled test set. Deferred until retrieval is implemented. |
| Cost + latency control | 🟡 P2 | LLM calls only on Boss Round (1 per 10-answer round). Caching: identical answers use cached grade. Streaming UI shows feedback as tokens arrive. Model tiering (cheap → expensive for high-value rounds) deferred. |

### Agentic workflows and tool use (MCP)

| Facet | Status | Where |
| --- | --- | --- |
| MCP server | ⏳ P3 | Term Rush exposes term bank + player progress as an MCP server — Claude Code (or any MCP client) can query it. `MCP` is a term in the game. Not yet implemented. |
| Tool-use loop | ✅ P3 | Content authoring pipeline: Dagster extracts dependencies → LLM enriches → validates against schema → loads → human review queue. Real structured tool calls (Claude API, schema-constrained output). `content-pipeline/` services. Verified E2E with multiple sources (dependency-manifest, ADR headings, Python class names, curated YAML). |
| Human-in-the-loop | ✅ P3 | Generated terms land in review-queue endpoint (`GET /api/review-queue`, `PATCH .../approve-or-reject`). Review UI + API prevent unreviewed terms from reaching live. content-service persists in database until approval. |
| Eval harness | ⏳ P3 | Not yet implemented. Golden set of terms; scoring agent output against schema. Prevents prompt-change regressions. Deferred. |

### Vector databases and embedding pipelines

| Facet | Status | Where |
| --- | --- | --- |
| pgvector | ⏳ P3 | HNSW index, cosine distance |
| **Why not Pinecone/Weaviate/Qdrant** | ❌ | ADR-0012. At this corpus size (~10³ terms) a dedicated vector DB is a second datastore to operate for zero benefit. Knowing when *not* to add infrastructure is the point. The ADR states the corpus size at which I'd switch. |

### Prompt / context engineering as engineering

| Facet | Status | Where |
| --- | --- | --- |
| Versioned prompts | ✅ P2 | In-repo `services/game/game_service/domain/rubric_prompt.py`: system + user prompts versioned. Changes flow through code review, not scattered f-strings. ADR-0013. |
| Snapshot tests | ✅ P2 | `tests/unit/test_llm_judge.py`: snapshot tests on `ClaudeRubricOutput` parse results. Prompt changes produce reviewable diffs of model output on fixed input set. |
| Structured output | ✅ P2 | `domain/grading.py::ClaudeRubricOutput` Pydantic model. LLM returns JSON matching the schema or grades fail gracefully to deterministic path. Parse failures logged + counted. |
| Context budgeting | 🟡 P3 | Not yet implemented. LLM calls include term definition + player answer. Budget (max ~4K tokens) implicit in prompt length + answer cap (512 chars). Explicit budgeting deferred. |
| Injection hardening | ✅ P2 | Player answer (free-text, 1-512 chars) flows into LLM prompt as JSON-escaped value. Instruction hierarchy: grading task → rubric → delimited answer. Output validated against schema. ADR-0013. |

### Fluency with AI coding assistants

| Facet | Status | Where |
| --- | --- | --- |
| Repo is agent-legible | ✅ P1 | `CLAUDE.md`: workspace structure, layering rules (domain-free, 4-layer pipeline), FastAPI conventions (Annotated deps, pydantic schemas), code style (Google docstrings, f-strings, pathlib). Pre-commit hooks enforce compliance. |
| Agent-enforceable invariants | ✅ | `import-linter` contracts in `services/game/pyproject.toml` — violations fail CI. Domain never imports infrastructure; API never imports domain directly. Machine-checked, not documented hope. |
| Workflow documented | 🟡 P1 | CLAUDE.md documents the review bar (reads every line himself), terse style, small reviewable increments. Process log in .remember/ tracks agent corrections. Full `docs/ai-assisted-development.md` deferred. |

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

## Deepening roadmap

Systematic approach to deepen coverage incrementally across all four dimensions
(horizontal breadth, vertical depth, emerging skills, and deliberate omissions).
Each session deepens one or two focus areas, moving items from L1→L2→L3→L4.

### L1→L2 priorities (robustness: error handling, edge cases, testing)

| Focus | Current | Next step | Why |
| --- | --- | --- | --- |
| Streaming UI | L1 | Add reconnection + timeout handling for network failures | SSE can fail mid-stream; need graceful fallback |
| Structured concurrency | L1 | Migrate manual `create_task()` to `TaskGroup` with timeouts | Guarantees cancellation; easier to reason about |
| GraphQL BFF | L1 | Resolve unused fields (`randomTerm`); validate N+1 patterns | Schema should match what clients actually use |
| Input validation | L2 | Comprehensive Pydantic audit (all endpoints + error messages) | Trust boundary; every gap is a risk |
| Observability logging | L2 | Verify all error paths are logged (no silent failures) | Debugging production requires complete traces |

### L2→L3 priorities (optimization: measurement, tuning, documented trade-offs)

| Focus | Current | Next step | Why |
| --- | --- | --- | --- |
| Real-time game loop | L2 | Measure 60fps under load; verify no dropped frames (React Profiler + Lighthouse) | Claims about performance are hollow without data |
| gRPC performance | L2 | Load test gRPC vs REST on term lookup; document latency gains | "High-frequency" claim needs proof |
| Prompt engineering | L2 | Snapshot tests for prompt changes; measure parse failure rate | Prompt regressions hide in iteration |
| LLM grading | L2 | Measure grade cache hit rate; cost per session under different modes | Economics matter at scale; baseline now |
| Async profiling | L2 | Audit event-loop blocking with `slow_callback_duration`; document any IO waits | Hidden sync calls become visible under load |

### L3→L4 priorities (generalization: abstractions, patterns, extensibility)

| Focus | Current | Next step | Why |
| --- | --- | --- | --- |
| API design (REST/gRPC/GraphQL) | L2 | Formalize protocol selection framework; document when to add a 4th protocol | Valuable because *why each is chosen*, not just that it exists |
| State management | L2 | Document state ownership matrix (server vs client vs cache); formalize rules | Clear contracts prevent bugs in distributed context |
| Caching strategy | Partial | Implement grade cache + rate limiter; document TTL trade-offs per use case | Three distinct patterns → generalize to cache taxonomy |
| Error handling | L2 | Formalize Result types; typed exceptions with structured feedback | Pattern emerges: domain errors vs infrastructure errors |
| Concurrency patterns | L1 | Extract reusable bounded-concurrency wrapper; apply to multiple use cases | `TaskGroup` + timeout pattern used everywhere |

### Emerging skills deepening

| Focus | Current | Next step | Why |
| --- | --- | --- | --- |
| RAG pipeline | Not started | Embed term definitions; hybrid search (vector + keyword); retrieval eval (Recall@k) | Differentiator: most RAG projects never measure retrieval quality |
| Agentic workflows | L1 (pipeline exists) | Eval harness with golden term set; prevent prompt-change regressions | Agents without measurement are demos, not systems |
| Vector databases | L0 (pgvector installed, unused) | Prove embedding quality; measure vector search latency vs keyword | Clarifies when pgvector stays (stays) vs when Pinecone enters |
| Prompt versioning | L1 (in-repo) | Add CI checks for prompt drift; snapshot tests on fixed input set | Prompts are code; treat as such |
| Cost estimation | L0 | Back-of-envelope: tokens/request, requests/session, LLM cost/MAU at scale | Matters for pitch; LLM-heavy projects need this number |

### Format for deepening sessions

When focusing on a depth area:

1. **Identify the L1 gap:** e.g., "Streaming UI has no reconnection logic"
2. **Write the test first:** e.g., "simulate network failure mid-stream, verify fallback"
3. **Implement the feature:** small, focused PR
4. **Measure if applicable:** e.g., "benchmark REST vs gRPC on 10k requests"
5. **Document the decision:** e.g., "why this timeout value, what trade-off we accepted"
6. **Update this table:** move item to next depth level; update "Next step"

---

## Job description mapper

Given a JD requirement or technical skill, jump to the relevant code and depth level.
Use this to quickly assess whether Term Rush covers a role's expectations or to identify gaps to fill.

### Backend / API

| JD phrase | Where in Term Rush | Depth | Gap? |
| --- | --- | --- | --- |
| "FastAPI / async Python" | `services/game/game_service/api/app.py`, `infrastructure/database.py` | L2 | Add event-loop profiling (slow callback detection) |
| "SQL / relational modeling" | `infrastructure/database.py`, `alembic/versions/` (8 migrations), `sql_uow.py`, `sql_repositories.py` | L2 | Benchmark queries with `EXPLAIN ANALYZE`; add query performance doc |
| "REST API design" | `api/routers/` (game rounds, leaderboard, answers), `api/schemas.py` (Pydantic) | L2 | Status code audit; breaking-change detection in CI |
| "gRPC / protobuf" | `game-service` → `content-service` term lookup, `term.proto`, generated stubs | L2 | Load test vs REST; latency measurement |
| "Structured logging / observability" | `infrastructure/logging.py` (JSON, OTel injection, redacted fields) | L2 | Verify all error paths logged; add metrics (Prometheus client imported) |
| "Event-driven architecture / message queues" | `infrastructure/kafka_event_publisher.py`, Kafka consumers (term-stats, cache invalidation), ADR-0011 | L2 | Add idempotent consumer; transactional outbox pattern |
| "Caching strategies" | Redis configured but unused; plan: LLM grade cache + rate limiter | L1 | Implement cache; measure hit rates by use case |
| "Database migrations" | `alembic/`, 8 migrations (Expand-contract pattern) | L2 | Add pre-migration validation; document rollback strategy |
| "Domain-driven design" | `domain/` (entities, value objects, use cases), `application/` (ports), `infrastructure/` (adapters) | L2 | Formalize domain ubiquitous language; ADR-style decision log |
| "Error handling / typed results" | `domain/grading.py` (GradeOutcome, GradeError), structured exceptions | L2 | Extend to all use cases; formalize Result types across codebase |

### Frontend / React

| JD phrase | Where in Term Rush | Depth | Gap? |
| --- | --- | --- | --- |
| "React 18+ / TypeScript strict" | `services/web/src/App.tsx`, `package.json` (React 19.2.8, TS 6.0), ESLint strict | L2 | Add React Profiler traces; measure 60fps under load |
| "Real-time UI / animations" | `useSprintCountdown.ts` (requestAnimationFrame, wall-clock sync) | L2 | Prove 60fps with Lighthouse; document frame-rate budget |
| "Client state management" | Local React state + refs (no external lib needed); OpenAPI client for server state | L2 | Document state ownership matrix; formalize rules |
| "SSE / streaming responses" | `submitAnswerStream.ts` (hand-rolled SSE parser, event framing) | L1 | Add reconnection + mid-stream timeout handling |
| "Accessibility (WCAG A11y)" | Keyboard navigation, ARIA live regions, speech input + language toggle, Playwright tests | L2 | axe-core audit; reduce-motion compliance testing |
| "CSS-in-JS / Tailwind v4" | `index.css` (Tailwind v4.3.3), shadcn components | L1 | Design token consistency; light/dark theme audit |
| "API client generation" | OpenAPI → TypeScript (openapi-ts), CI regenerates + type-checks | L2 | Breaking-change detection; schema drift alerts in PR |
| "E2E testing" | Playwright tests (daily-20, survival, classic, boss, settings modes), mocked backend | L2 | Extend to real-backend integration tests; add performance assertions |

### Distributed systems / DevOps

| JD phrase | Where in Term Rush | Depth | Gap? |
| --- | --- | --- | --- |
| "Docker / containerization" | Multi-stage `services/game/Dockerfile`, non-root user, healthcheck | L2 | Add image scanning; base digest pinning |
| "Docker Compose" | `compose.yml` (game-service, content-service, postgres, redis), health checks | L2 | Add observability stack profile; document scaling limits |
| "Kubernetes (kind)" | Not implemented yet; ADR-0015 reserves for P4 | L0 | Proof-of-concept on kind; helm charts |
| "CI/CD pipeline" | `.github/workflows/ci.yml` (lint, type-check, test, import-linter) | L2 | Add frontend tests to CI; dependency scanning gates |
| "Monitoring / observability" | JSON logging with OTel injection; Prometheus imported | L1 | Wire Prometheus metrics; add Grafana dashboard; SLO tracking |
| "Kafka / event streaming" | Kafka (Redpanda locally), E2E consumers verified (term-stats, cache invalidation) | L2 | Add idempotent consumer; DLQ + replay capability |
| "Secrets management" | `.env.example` tracked (safe schema), `.env` gitignored, no CLI args | L2 | Audit for hardcoded secrets; credential rotation strategy |
| "Load testing" | Not started; k6 reserved for P4 | L0 | Benchmark under concurrent load; derive HPA thresholds |

### AI / LLM / RAG

| JD phrase | Where in Term Rush | Depth | Gap? |
| --- | --- | --- | --- |
| "LLM-based grading / structured output" | `infrastructure/llm_judge.py`, `domain/grading.py` (ClaudeRubricOutput Pydantic model) | L2 | Cost tracking; latency measurement; fallback validation |
| "Prompt engineering / versioning" | `domain/rubric_prompt.py` (in-repo, versioned), snapshot tests | L2 | Add CI checks for prompt drift; golden test set |
| "Prompt injection defense" | JSON-escaped player answers, instruction hierarchy, output schema validation | L2 | Adversarial test cases; red-team the grader |
| "RAG / semantic search" | pgvector extension installed; not yet implemented | L0 | Implement embedding pipeline; hybrid search; Recall@k evaluation |
| "Cost + latency control" | LLM calls only on Boss Round (1 per 10 answers); in-memory grade cache | L1 | Measure cache hit rate; cost per session; model tiering strategy |
| "Agentic workflows / tool use" | Dagster pipeline: extract → enrich → validate → load → review queue | L2 | Eval harness (golden terms); prevent prompt-change regressions |
| "Human-in-the-loop workflows" | Review queue endpoint (GET, PATCH approve/reject); terms persist until approval | L2 | UI for human review; audit trail of decisions |

### Architecture / System Design

| JD phrase | Where in Term Rush | Depth | Gap? |
| --- | --- | --- | --- |
| "Microservices architecture" | Two services (game-service, content-service), gRPC internal, REST public | L2 | Service-to-service contract validation; chaos testing |
| "Domain-driven design" | Domain layer (framework-free), application (ports/protocols), infrastructure (adapters) | L2 | More ADRs documenting domain concepts; ubiquitous language |
| "Clean architecture" | 4-layer separation enforced by import-linter contracts | L2 | Formalize layer responsibilities; add documentation |
| "Design patterns" | Strategy (multiple graders: exact, alias, fuzzy, LLM), Factory, Repository, Unit of Work | L2 | Document pattern catalog; link to code examples |
| "Technology trade-offs" | ADRs for protocol choice (REST/gRPC/GraphQL), vector DB decision, auth approach | L2 | Add ADRs for cache/queue/persistence choices; doc reversal points |
| "Scalability" | Denormalized leaderboard queries, Kafka event log, eventual consistency | L1 | `docs/scaling.md`: system at 100 users → 100k → 10M; bottleneck analysis |
| "Reliability / fault tolerance" | LLM grading fails gracefully to deterministic path; Kafka consumers retry | L1 | Circuit breaker pattern; chaos test (kill consumer, verify recovery) |

### Data / SQL

| JD phrase | Where in Term Rush | Depth | Gap? |
| --- | --- | --- | --- |
| "SQL / relational schema" | `game_rounds` (JSON + denormalized fields), `term_stats` (columnar), `content_service.terms` (8-table normalized) | L2 | Query performance audit (EXPLAIN ANALYZE); index strategy doc |
| "Alembic / data migrations" | 8 migrations, expand-contract pattern for destructive changes | L2 | Add pre-migration validation; zero-downtime deployment strategy |
| "Indexing / query optimization" | Leaderboard indexed on (mode, total_score) for efficient sorting | L1 | Profile with `EXPLAIN ANALYZE`; document index strategy |
| "NoSQL trade-offs" | JSON blob for rounds (ADR-0005: justifies choice over MongoDB) | L2 | Add more NoSQL examples (when would we switch to document DB) |
| "FSRS / spaced repetition" | Not yet implemented (P3+) | L0 | Implement FSRS state tracking; measure learning curve |

### Useful when reading a JD

1. **Scan the tech stack** in the JD (e.g., "FastAPI + React + Postgres + Kafka")
2. **Look up each skill** in the Job Description Mapper above
3. **Check the code location** — verify it exists and read the actual implementation
4. **Check the depth level** — is L2 (robust) enough for the role, or should you deepen to L3 (optimized)?
5. **Identify gaps** — the "Gap?" column tells you what's missing (e.g., "Add event-loop profiling")
6. **Plan a skill fill-in:** if a gap is critical for the role, add it to the deepening roadmap above
7. **Link in the cover letter:** "Term Rush demonstrates [skill] at [depth] — see [file location]"

---

## How to read this as a reviewer

Fastest path to judging whether I can actually do this work:

1. `docs/adr/` — the decisions, especially the negative ones
2. `docs/scaling.md` — the system design thinking (P5)
3. `services/game/game_service/domain/` — the code with no framework in it
4. `docs/performance.md` — whether I measure or guess (P4)
5. This file — both breadth (what exists) and depth (how sophisticated)
