# ADR-0008: Decoupled Migrations via 12-Factor Process Model

- **Status:** Accepted
- **Date:** 2026-09-18
- **Relates to:** ADR-0006 (one-image monolith), Phase 1d (PostgreSQL foundation)

## Context

The API and database schema must evolve together, but their deployment mechanisms differ:

- **Local development**: migrations and API run in the same process
- **Docker Compose**: services are separate containers but orchestrated
- **Kubernetes**: migrations run as Jobs, API as Deployments—entirely independent lifecycles

Coupling migrations into the API bootstrap means:

- Schema changes block API startup
- Rollback requires API restart
- Retry logic must live in the API
- Multi-region deployments must wait for one migration to finish before advancing others
- Development and production binaries behave differently (violates 12-factor parity)

## Decision

One binary (`services/game/bin/run.py`) runs everywhere. The `PROCESS_TYPE` environment variable determines behavior—migrations or API. This honors the 12-factor app principle: same code, different config.

### Implementation

**Same binary, different PROCESS_TYPE:**

```bash
PROCESS_TYPE=migrate python bin/run.py    # Run migrations
PROCESS_TYPE=api python bin/run.py        # Start API
```

**Local development & Docker Compose (sidecar pattern):**

```bash
# Run manually before starting API
PROCESS_TYPE=migrate python services/game/bin/run.py

# Or via compose
docker compose --profile tools run migrate
```

**Kubernetes (Job pattern):**

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: term-rush-migrate
spec:
  template:
    spec:
      containers:
      - name: migrate
        image: term-rush:latest
        env:
        - name: PROCESS_TYPE
          value: migrate
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: term-rush-secrets
              key: database-url
```

Then deploy API Deployment as usual with `PROCESS_TYPE=api`.

**Fallback for missing migrations:**
API startup does NOT check schema state. This is intentional: migrations are caller's responsibility. Failed migrations fail loudly (Alembic exits non-zero), which Kubernetes Jobs detect and retry.

## Consequences

### Positive

- ✅ Schema changes decouple from API restarts
- ✅ Migrations can be retried/replayed independently
- ✅ Scales to multi-region (migrate leader, then deploy replicas)
- ✅ Works across dev, staging, production with the same `bin/migrate.py`
- ✅ Kubernetes Jobs handle retry and backoff; no custom logic needed

### Negative

- ❌ Human error: forget to migrate → API hits missing columns → 500 errors
- ❌ Requires discipline: migrations MUST run before API starts
- ❌ No built-in guardrail in the API

### Mitigation

- Kubernetes: Job runs as part of release pipeline; Deployment depends_on Job
- Docker Compose: document sidecar pattern in README
- Local dev: Makefile/Justfile target to run migrate + run in order
- Future: readiness probe could check schema version (Phase 2+)

## When I Would Change This

- If migrations become so frequent (>daily) that decoupling overhead exceeds benefit
- If operational complexity of Job orchestration exceeds internal capacity
- If incident response needs migrations to be reversible without downtime (would require expand-contract pattern + feature flags)

Currently (Phase 1d), migrations are infrequent (once per phase boundary), so decoupling is a clean win.
