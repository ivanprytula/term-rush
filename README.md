# Term Rush — Full-Stack Learning Platform

A portfolio-grade full-stack application for learning and spaced repetition of CS abbreviations and concepts.

This repo is built to demonstrate production engineering practices — the game is the
vehicle, not the deliverable. Scope and infrastructure choices are sized for that goal
(see [ADR-0001](./docs/adr/0001-record-architecture-decisions.md)), not for a
minimal shipping product.

**Status:** Phase 1b complete (domain + application layer). Phase 1c (FastAPI) in progress.

## Backend (Phase 1)

- **Domain:** Term entities, grader chain (exact → alias → fuzzy), four-slice rubric scoring (30% expansion, 40% concept, 20% purpose, 10% example).
- **Application:** Use cases, typed results, Ports (Protocols) for repository/cache/events.
- **Infrastructure:** In-memory adapters for stateless deployments; SQL/Redis adapters planned Phase 1d.
- **API:** FastAPI (planned Phase 1c).
- **Architecture:** Clean Architecture with machine-enforced layering via `import-linter`.
- **Testing:** 39+ tests with property-based testing (Hypothesis) and regression oracles pinned against the prototype.

## Frontend (Prototype → React, Phase 1e)

The original `index.html` prototype lives in the root; it will be deleted once the React client reaches parity.

- Falling/moving terms that can be tapped/clicked.
- Type an expansion/definition.
- Browser speech recognition where supported.
- Score, streak, level and timer.

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

See [docs/skills-map.md](./docs/skills-map.md) for capability coverage (what's done, planned, deferred, skipped and why).

## Next Steps

- **Phase 1c:** FastAPI wiring, request/response models, answer submission endpoint
  — done when a client can submit an answer over HTTP and get a real grade back.
- **Phase 1d:** PostgreSQL + Redis, Alembic migrations
  — done when sessions and answers survive a restart instead of living in memory.
- **Phase 1e:** React client, delete `index.html`
  — done when the prototype UI is fully replaced and removed.
- **Phase 2:** LLM-based grading (Celery + Claude), streaming rubric feedback
  — done when grading quality exceeds the deterministic rubric and feedback streams live.
- **Phase 3:** Microservices split (content-service), Kafka event log, GraphQL BFF
  — done when a second service exists and talks to the first over the network, not imports.
- **Phase 4:** GCP deployment (Cloud Run), AWS modules (reviewable), Kubernetes (local kind)
  — done when the app runs on a real cloud target, reachable over HTTPS.
- **Phase 5:** Documentation and technical narrative
  — done when a reviewer can read the scaling/performance story without asking questions.

Later / not yet scheduled to a phase:

- Game modes: Sprint, Survival, Boss Round, Daily 20.
- Separate term knowledge from presentation: term, aliases, explanation, examples, difficulty, tags, prerequisites.
- Spaced repetition (FSRS/SM-2 style) instead of repeating random terms.
- Score semantic quality, not only string similarity.
- AI/LLM terms as a versioned content pack.
- Offline PWA support with IndexedDB.
