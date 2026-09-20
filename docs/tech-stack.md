# Tech Stack

What each service is built with and why. For architectural reasoning behind
individual choices, see the linked ADRs; this page is the inventory, not the
rationale.

## Backend — game-service, content-service

- **Python 3.14**, [uv](https://docs.astral.sh/uv/) workspace
  (`services/*`, `libs/*` members) for dependency management and the
  monolith image build ([ADR-0001](adr/0001-record-architecture-decisions.md)).
- **FastAPI** + **uvicorn** — REST APIs for both services.
- **Pydantic v2** — request/response schemas, frozen domain models
  (`Term`, `Session`, `EventEnvelope`).
- **SQLAlchemy 2.0** (async, `asyncpg` driver) + **Alembic** — persistence
  and migrations, one history per service
  ([ADR-0008](adr/0008-decoupled-migrations.md)).
- **PostgreSQL** — one database per service (`term_rush`,
  `term_rush_content`), not a shared instance/schema.
- **Redis** — session cache for game-service.
- **gRPC** (`grpcio` + `grpc_tools.protoc`) — game-service's read path to
  content-service's term data; contract owned by `libs/term-proto`. ADR for
  this choice is pending (reserved as ADR-0009 in
  [skills-map.md](skills-map.md)).
- **Anthropic Claude API** (`anthropic` SDK) — LLM rubric grading escalation
  on ambiguous answers, streamed over SSE (`sse-starlette`).
- **import-linter** — machine-enforced Clean Architecture layering and
  service-isolation contracts, run in `just check`.
- **OpenTelemetry** (API + SDK, Prometheus exporter, FastAPI instrumentation)
  — metrics/tracing scaffolding.
- **pytest** (`pytest-asyncio`, `pytest-cov`) + **Hypothesis** — unit,
  integration, and property-based tests; regression oracle pinned against
  the original prototype's `similarity()`.
- **ruff** (lint + format) and **ty** — quality gates, run per-service.

## Frontend — services/web

- **React 19** + **TypeScript**, built with **Vite 8** (`@vitejs/plugin-react-swc`).
- **Tailwind CSS v4** (`@tailwindcss/vite` plugin) — styling.
- **radix-ui**, **shadcn**, **class-variance-authority**, **lucide-react** —
  headless UI primitives and component scaffolding.
- **axios** — HTTP client.
- **@hey-api/openapi-ts** — generates a typed API client from game-service's
  OpenAPI schema (`services/web/src/client/`, gitignored, regenerated on
  demand — see [services/web/README.md](../services/web/README.md)).

## Infrastructure & Tooling

- **Docker** — one shared image for every backend service; `PROCESS_TYPE`
  env var (12-factor dispatch) and `CMD`/`command:` override select
  behavior at runtime ([ADR-0006](adr/0006-one-image-for-all-services.md)).
- **Docker Compose** — local orchestration: `postgres`, `postgres-content`,
  `redis`, `game`, `content`, one-off `migrate`/`migrate-content` containers
  (`profiles: [tools]`).
- **Just** (`Justfile`) — task runner: setup, tests, quality gates, arch
  contracts, migrations, seeding, dev servers, smoke tests.
- **grpcurl** / **grpcui** — manual inspection of content-service's gRPC
  contract (`just grpc-ui`); see [development.md](../development.md).
- **pre-commit** (`prek`) — lint/format hooks.
- **mdlint** — Markdown lint (blank lines around lists, fenced code block
  language, line length) for all docs, ADRs, and this file.

## Planned, not yet in the stack

- **Kafka** (or Redpanda) — event log for `TermPublished`/`AnswerGraded`
  (reserved as ADR-0011, Phase 3, optional/stretch).
- **Strawberry GraphQL** — BFF aggregating game-service's REST API
  (reserved as ADR-0010, Phase 3, optional/stretch).
- **Cloud Run / Kubernetes (kind)** — deployment targets (Phase 4).
