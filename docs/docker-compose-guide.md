# Docker Compose Guide

Local stack mirrors cloud topology. Two recipes: hot-reload dev, containerized test.

## Commands

See [Running Services](../development.md#just-recipes-reference) in the development guide for the complete Just recipes reference.

**Quick start:**

- `just up` — Start postgres, postgres-content, redis, redpanda (background)
- `just dev` — Start game + content with auto-reload (native Python; infra in Docker)
- `just docker-stack` — Run all services in Docker (production parity)
- `just down-soft` — Stop containers, keep DB volumes
- `just down` — Stop containers, delete DB volumes

## Toggles (Edit Justfile, Uncomment)

Optional services via `# TOGGLE:` comments in Justfile:

**Pipeline (Dagster :3000):**

- `just dev`: uncomment pipeline toggle
- `just docker-stack`: uncomment pipeline toggle

**Web (Vite :5173):**

- `just dev`: uncomment web toggle
- `just docker-stack`: uncomment web toggle

## Ports & URLs

| Service | Port | URL |
| --- | --- | --- |
| game | 8000 | `localhost:8000/docs` |
| content | 8001 | `localhost:8001/docs` |
| content gRPC | 50051 | (internal) |
| pipeline | 3000 | `localhost:3000/asset_graph` |
| web | 5173 | `localhost:5173` |
| postgres | 5432 | (internal) |
| postgres-content | 5433 | (internal) |
| redis | 6379 | (internal) |
| redpanda | 9092 | (internal, optional) |

## Workflow

**Backend dev (auto-reload):**

```bash
just dev
# Edit code → auto-reload
# Ctrl-C to stop
```

**Docker test (production parity):**

```bash
just docker-stack
docker compose logs -f [service]
just down-soft
```

**With pipeline:**
Edit Justfile, find pipeline toggle, uncomment, run.

**With web:**
Edit Justfile, find web toggle, uncomment, run.

## Troubleshooting

| Problem | Solution |
| --- | --- |
| Service won't start | `docker compose logs [service]` |
| Migrations missing | `docker compose run --rm migrate` (then restart) |
| Pipeline/web not running | Check Justfile toggle is uncommented |
| Out of disk | `docker system prune -a --volumes` |

## Architecture

**Services:** game (gRPC ↔ content), content (REST ↔ pipeline), pipeline (REST → content).

**Data:** Two postgres (game, content-service), redis (cache), redpanda (optional Kafka).

**Dependency order:** postgres/redis → content → game. Pipeline after content.

**Environment parity:**

- Local: Docker Compose orchestration
- Cloud: K8s pod topology, same service contracts
- Only difference: infrastructure layer (local Docker ↔ cloud managed services)

See `compose.yml` for full service definitions. Service isolation enforced via `import-linter`.
