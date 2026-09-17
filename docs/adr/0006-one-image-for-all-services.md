# ADR-0006: One container image for all services

- **Status:** Accepted
- **Date:** 2026-09-17
- **Related:** ADR-0003 (principles before frameworks)

## Context

The architecture is microservices — `game-service` now, `content-service` in Phase 3,
plus Celery workers and Kafka consumers. The reflex is one image per service.

At this stage that reflex is wrong. There is one service. Splitting now buys isolation
nobody needs and costs a build matrix, N Dockerfiles drifting apart, and N dependency
resolutions to keep coherent.

Meanwhile the uv workspace already gives a single lockfile and one resolution across
all members — the property a per-service split would immediately break.

## Decision

**One image containing every workspace member. `CMD` selects which one runs.**

```bash
docker run term-rush                                     # game-service (default)
docker run term-rush uvicorn content_service.api.app:app # another member
docker run term-rush celery -A game_service.worker worker
```

Build once, deploy the same artifact as several differently-configured containers.
Cloud Run and Kubernetes both address this by command override, so the deployment
story is unaffected.

Code separation is enforced where it actually matters — at the **import boundary**, not
the image boundary. import-linter contracts already forbid service→service imports and
lib→service imports. Services are separable because nothing couples them, not because
a Dockerfile keeps them apart.

## What this costs

- **Image size.** Every container carries every service's dependencies. At this
  dependency count it is tens of megabytes; not worth a build matrix.
- **Blast radius of a rebuild.** Changing `content-service` rebuilds the image
  `game-service` ships from. Mitigated by layer caching: the dependency layer is keyed
  on the lockfile and survives source edits.
- **Weaker isolation.** A vulnerability in one service's dependency is present in all
  containers. Accepted at this scale; it is the main thing that would flip the decision.

## When I would change this

Split into per-service images when **any** of these becomes true:

1. Dependency sets diverge enough that the shared image is materially bloated — a
   service pulling ML libraries that an API container has no use for.
2. Build time exceeds ~3 minutes, making the shared rebuild an actual bottleneck.
3. Independent deploy cadence is needed — shipping `content-service` without
   redeploying `game-service`.
4. Security review requires per-service dependency isolation.

The split is a change to **one file**. The workspace layout, the import contracts and
the `CMD`-override deployment pattern all stay as they are. That is the point of doing
it this way: the cheap option now does not foreclose the expensive one later.

## Amendment: Dockerfile path (2026-09-17)

The Dockerfile lives at `services/game/Dockerfile`, not the repo root, despite still
building the whole monolith (every workspace member, per the decision above). Build
context stays the repo root (`docker build -f services/game/Dockerfile .`) so the
workspace-wide `uv sync` keeps working unmodified. The path does not imply a
per-service image yet — that split is still the one-file change described above, now
starting from this location instead of the root.

## Alternatives considered

**One Dockerfile per service, sharing a base image.** The eventual answer. Rejected
for now: three files to keep in sync for one running service.

**Dockerfile targets (`--target game`).** One file, per-service images, no duplication.
Genuinely close — rejected only because the runtime layers would be near-identical
until dependency sets diverge, so it adds build-matrix complexity for no present
benefit. This is the likely first step when criterion 1 or 3 triggers.
