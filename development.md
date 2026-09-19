# Development

## Quick Start

Install dependencies and run checks:

```bash
just sync         # Install the workspace
uv run prek install  # One-time: install the pre-commit git hook
just check        # Lint, type-check, verify architecture, run tests
```

Without `prek install`, checks only run when you invoke `just check`/`just precommit`
manually — they do not run automatically on `git commit`.

## Project Structure

See [Workspace Structure](./CLAUDE.md#workspace-structure) in CLAUDE.md — kept in
one place to avoid drift.

## Architecture

The project follows Clean Architecture with enforced layering via `import-linter`
(see [Architecture invariants](./CLAUDE.md#architecture-invariants--machine-enforced)
in CLAUDE.md). Every service boundary is a Protocol (`typing.Protocol`);
implementations are swappable.

See [ADR-0003](./docs/adr/0003-principles-before-frameworks.md) for the design principle.

## Testing

```bash
just test                          # Run all tests
just test services/game/tests/unit/test_domain.py  # Run specific test file
just coverage                      # Run tests with coverage report
```

Tests use `pytest` with property-based testing via `hypothesis`. Domain tests pin behavior against the original prototype's JavaScript implementation to prevent silent regressions.

## Code Quality

All tooling is configured in `pyproject.toml`:

```bash
just quality       # ruff check + ruff format + ty
just arch          # Verify import-linter contracts
just check         # quality + arch + test (full gate)
```

- **Linting:** `ruff` (line-length 88, import sorting, auto-fix enabled)
- **Type checking:** `ty`
- **Architecture:** `import-linter` (layering, domain isolation, service isolation contracts)

## Running Services

Start supporting services for local development:

```bash
just up   # Start postgres and redis
just down # Stop postgres and redis
just migrate       # Run database migrations (requires postgres running)
just run-dev       # Run API server with hot-reload (requires postgres + migrations)
just smoke         # Full integration test: build image, start, probe /health and /ready
```

The monolith image contains all workspace members. Service selection happens at runtime via `PROCESS_TYPE` env var (12-factor):

- `PROCESS_TYPE=migrate` — Run Alembic migrations synchronously
- `PROCESS_TYPE=api` — Run FastAPI server asynchronously

See [ADR-0006](./docs/adr/0006-one-image-for-all-services.md) for the image strategy.

### Database Migrations

Same binary runs everywhere; behavior determined by `PROCESS_TYPE` env var:

```bash
# Local: start postgres first
just up

# Local: run migrations
just migrate

# Local: run API (assumes migrations complete)
just run-dev

# Docker Compose sidecar (before starting game service)
docker compose --profile tools run migrate

# Kubernetes Job (separate from Deployment)
apiVersion: batch/v1
kind: Job
metadata:
  name: migrate
spec:
  template:
    spec:
      containers:
      - name: migrate
        image: term-rush:latest
        env:
        - name: PROCESS_TYPE
          value: migrate
```

Migrations and API are separate processes; API assumes schema is ready.

`docker compose up` reads `compose.yml` and `compose.override.yml` together —
Compose merges the override automatically, no flag needed. `compose.yml` defines the
base build/ports; `compose.override.yml` adds local-dev extras (hot reload via
`--reload` and bind mounts, healthcheck, `docker compose watch` sync/rebuild rules).

## Secrets Generation

Generate secure random values for environment variables with:

```bash
uv run python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Use this for `SECRET_KEY`, `FIRST_SUPERUSER_PASSWORD`, and other sensitive defaults. Store generated values in `.env` (gitignored), never in code or `compose.yml`.

## Documentation

- `docs/adr/` — Architectural Decision Records (decisions, trade-offs, reversibility conditions)
- `docs/skills-map.md` — Capability coverage (what's implemented, what's planned, what's deferred)

Every decision that shapes the codebase should have an ADR, including deliberate non-decisions ("why NOT X").

## Phase Status

**Phase 1a (Domain)** — ✅ Complete. Domain entities, grader chain, rubric scoring, 35+ tests.

**Phase 1b (Application)** — ✅ Complete. Ports, in-memory adapters, use cases, 4 new tests.

**Phase 1c (API)** — ✅ Complete. FastAPI wiring, Pydantic schemas, `/answers/submit` endpoint, 7 integration tests.

**Phase 1d (PostgreSQL)** — ✅ Complete. Alembic migrations, TermModel,
SQLTermRepository, SQLUnitOfWork, seed script; verified end-to-end against
a live container.

**Phase 1e (Sessions)** — ✅ Complete. Session/SubmittedAnswer domain
entities, SessionRepository port + adapters, `GET /sessions/{id}`;
verified state survives a container restart.

**Phase 1f (React client)** — ✅ Complete (minimal scope). `services/web/`
covers the core submit/grade loop against the real API. Prototype parity
(falling terms, voice input, settings) not yet scheduled — see
[Next Steps](./README.md#next-steps).

See [Next Steps](./README.md#next-steps) in the README for the full roadmap.
