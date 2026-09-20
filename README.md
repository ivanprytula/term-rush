# Term Rush — Full-Stack Learning Platform

A portfolio-grade full-stack application for learning and spaced repetition of CS abbreviations and concepts.

This repo is built to demonstrate production engineering practices — the game is the
vehicle, not the deliverable. Scope and infrastructure choices are sized for that goal
(see [ADR-0001](./docs/adr/0001-record-architecture-decisions.md)), not for a
minimal shipping product.

**Status:** Phase 1a–1f complete. Phase 2 (LLM-based grading) not yet started.

## Backend (Phase 1)

- **Domain:** Term entities, grader chain (exact → alias → fuzzy),
  four-slice rubric scoring (30% expansion, 40% concept, 20% purpose, 10%
  example). Session entity records a play-through's answer history.
- **Application:** Use cases, typed results, Ports (Protocols) for
  repository/cache/events.
- **Infrastructure:** In-memory adapters for stateless deployments; SQL
  adapters (SQLAlchemy + Alembic) for terms and sessions in PostgreSQL.
- **API:** FastAPI — `POST /sessions/{id}/answers/submit`, `GET
  /sessions/{id}`, `GET /terms/random`.
- **Architecture:** Clean Architecture with machine-enforced layering via
  `import-linter`.
- **Testing:** 66+ tests with property-based testing (Hypothesis) and
  regression oracles pinned against the prototype.

## Frontend (Prototype + React client)

The original `index.html` prototype lives in `.local-dev/` (arcade UX:
falling terms, voice input, score/streak/timer) and stays until the React
client reaches parity with it.

`services/web/` is a minimal React client (Vite + React 19 + TypeScript +
Tailwind v4) covering the core loop: fetch a random term, submit an answer
against the real API, show the graded result. It doesn't yet replicate the
arcade presentation — see [services/web/README.md](./services/web/README.md)
for dev setup and [docs/game-rules.md](./docs/game-rules.md) for how
scoring works (also readable in-app via the "How to play" panel).

## Quick Start

```bash
just sync      # Install dependencies
just check     # Run all quality gates (lint, type-check, arch, tests)
just smoke     # Build Docker image and probe /health, /ready
```

See [development.md](./development.md) for the full development guide.

## Architecture & Decisions

Every significant decision is documented in `docs/adr/`:

- **ADR-0001:** Workspace structure (uv, editable installs, monolith image)
- **ADR-0002:** Grading thresholds (why 0.62 for fuzzy accept)
- **ADR-0003:** Principles before frameworks (domain stays framework-free)
- **ADR-0004:** Term bank structure (self-reference terms in the game domain)
- **ADR-0005:** Data engineering and Dagster integration
- **ADR-0006:** One container image for all services (monolith → per-service when needed)
- **ADR-0007:** Flat service layout (no per-service namespaces yet)

See [docs/skills-map.md](./docs/skills-map.md) for capability coverage
(what's done, planned, deferred, skipped and why), and
[docs/tech-stack.md](./docs/tech-stack.md) for the full technology
inventory.

## Next Steps

- ~~**Phase 1d:** PostgreSQL adapter for terms, run migrations, seed test
  data~~ — done: terms load from the database, `POST /answers/submit`
  verified end-to-end.
- ~~**Phase 1e:** Session persistence (SQLAlchemy Session entity,
  Alembic)~~ — done: session state survives a container restart, verified
  live.
- ~~**Phase 1f:** React client~~ — done (minimal scope): `services/web/`
  covers the core submit/grade loop against the real API. Deleting
  `.local-dev/index.html` is deferred until the client reaches parity with
  its arcade UX (falling terms, voice input, settings, score/streak/timer)
  — not yet scheduled to a phase.
- ~~**Phase 2:** LLM-based grading (Claude), streaming rubric feedback~~ —
  done: grading quality exceeds the deterministic rubric (concept, purpose,
  and example scored, not just expansion), feedback streams live over SSE,
  verified end-to-end. Celery was scoped out: a synchronous in-request call
  is fast enough at current latency/throughput; revisit if that changes.
- **Phase 3:** Microservices split (content-service), Kafka event log, GraphQL BFF
  — done when a second service exists and talks to the first over the network, not imports.
- **Phase 4:** GCP deployment (Cloud Run), AWS modules (reviewable), Kubernetes (local kind)
  — done when the app runs on a real cloud target, reachable over HTTPS.
- **Phase 5:** Documentation and technical narrative
  — done when a reviewer can read the scaling/performance story without asking questions.

Later / not yet scheduled to a phase:

- React client parity with the `.local-dev` prototype (falling terms, voice
  input, settings, score/streak/timer), then delete the prototype.
- Game modes: Sprint, Survival, Boss Round, Daily 20.
- Separate term knowledge from presentation: term, aliases, explanation, examples, difficulty, tags, prerequisites.
- Spaced repetition (FSRS/SM-2 style) instead of repeating random terms.
- Score semantic quality, not only string similarity.
- AI/LLM terms as a versioned content pack.
- Offline PWA support with IndexedDB.
