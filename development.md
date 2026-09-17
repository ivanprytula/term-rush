# Development

## Quick Start

Install dependencies and run checks:

```bash
just sync         # Install the workspace
uv run prek install  # One-time: install the pre-commit git hook
just check        # Lint, type-check, verify architecture, run tests
just coverage     # Run tests with coverage report
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

## Docker

```bash
just build         # Build the monolith image
just run           # Run the API locally (port 8000)
just smoke         # Build, start, probe /health and /ready, tear down
```

The monolith image contains all workspace members. Service selection happens at runtime via `CMD` override.

See [ADR-0006](./docs/adr/0006-one-image-for-all-services.md) for the image strategy.

`docker compose up` reads `compose.yml` and `compose.override.yml` together —
Compose merges the override automatically, no flag needed. `compose.yml` defines the
base build/ports; `compose.override.yml` adds local-dev extras (hot reload via
`--reload` and bind mounts, healthcheck, `docker compose watch` sync/rebuild rules).

## Documentation

- `docs/adr/` — Architectural Decision Records (decisions, trade-offs, reversibility conditions)
- `docs/skills-map.md` — Capability coverage (what's implemented, what's planned, what's deferred)

Every decision that shapes the codebase should have an ADR, including deliberate non-decisions ("why NOT X").

## Phase Status

**Phase 1a (Domain)** — ✅ Complete. Domain entities, grader chain, rubric scoring, 35+ tests.

**Phase 1b (Application)** — ✅ Complete. Ports, in-memory adapters, use cases, 4 new tests.

**Phase 1c (API)** — In progress. FastAPI wiring, request/response models, `POST /answers/submit`.

See [Next Steps](./README.md#next-steps) in the README for the full roadmap.
