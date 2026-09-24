# Term Rush — Developer Onboarding

**Status:** Interim. Updated alongside README.md, development.md, ADRs.

## What It Is

Full-stack CS learning platform (flashcard game). Portfolio project—designed to be read and defended line-by-line. Production patterns: three services, clean architecture, event-driven caching, LLM grading.

## The Stack in One Table

| Layer | Tech | Owns | Key Gotcha |
|-------|------|------|------------|
| **API** | FastAPI (REST) + GraphQL | game (grading, sessions), content (terms) | Two services = two databases |
| **Services** | 3 independent | game :8000, content :8001, pipeline :3000 | gRPC (game→content) + Kafka (events) |
| **Architecture** | Clean layers | `api → infrastructure → application → domain` | Domain is framework-free (enforced) |
| **Data** | PostgreSQL (2) + Redis | game DB (sessions), content DB (terms), Redis cache | gRPC bridges the databases |
| **Cache** | in-memory (gRPC) + Redis | Terms (TTL + event-driven eviction), grades (unbounded, deterministic) | Event eviction: same grade per term+answer |
| **Pipeline** | Dagster | Extract → Enrich (LLM) → Validate → Load | Optional; runs standalone |
| **Frontend** | React 19 + Vite | Calls game-service REST/GraphQL | Proxies to :8000 in dev |
| **Quality** | ruff + ty + import-linter + pytest | Pre-commit hooks, CI gate | `just check` before commit |

## How It Works (Mental Model)

**Player submits answer → game-service grades it:**

1. Fetch term from content-service (gRPC), cache it (TTL 300s)
2. Run deterministic grader (exact → alias → fuzzy match)
3. If partial + LLM enabled, call Claude for deeper scoring
4. Store session state in game DB
5. Publish `AnswerGraded` event (Kafka)

**Author updates a term → invalidate cache:**

1. content-service writes term, publishes `TermPublished` event
2. game-service's background consumer evicts that term from cache
3. Next player's answer fetches fresh term definition
4. TTL (300s) is fallback if Kafka is down

**Why two databases?** Content-service owns terms (RESTful updates + gRPC reads). Game-service owns sessions (player state, answer history). Separation = independent scaling + clear ownership.

**Why event-driven cache eviction?** Same answer to same term always scores the same (deterministic). But term definitions can change—when they do, old cached definitions are stale. Events tell game-service "that term changed" immediately, not on TTL.

**Why grade cache has no eviction?** Deterministic = input (term_id + answer) uniquely determines output (GradeOutcome). Nothing external invalidates it. Process lifetime = cache lifetime. (Not an oversight; a consequence of determinism.)

## Start Here (Concrete Steps)

```bash
# 1. Install workspace (one-time)
just sync

# 2. Read the quickest onboarding (this file + README.md)
cat README.md

# 3. Start the stack
just up              # postgres + redis (background)
just dev             # game + content with auto-reload

# 4. Verify in another terminal
curl localhost:8000/docs        # FastAPI Swagger UI
curl localhost:8001/docs        # content-service API
just test                         # 400+ tests pass

# 5. Make a change (tests still pass)
# Edit services/game/game_service/domain/grader.py
# Save → auto-reload → test again

# 6. Before committing
just check  # Lint + type-check + arch + tests
```

## What Each `just` Recipe Does

See [Just Recipes Reference](../development.md#just-recipes-reference) in the development guide for the complete reference.

**Quick start commands:**

- `just sync` — Install dependencies
- `just up` — Start postgres + redis (background)
- `just dev` — Start game + content with auto-reload
- `just test` — Run all tests
- `just check` — Lint + type-check + arch + tests (before commit)

**Toggles (edit Justfile, uncomment):**

- Pipeline: `docker compose up -d --profile pipeline pipeline` → :3000
- Web: `docker compose up -d --profile dev web` → :5173

## Five Things You'll Hit (and How to Think About Them)

### 1. Two Databases

Content-service has its own postgres (:5433). Game-service has its own (:5432).

- **Why?** Services own their data. Independent deployment = independent schemas.
- **How to avoid confusion:** `PYTHONPATH=services/content` and separate `DATABASE_URL` per service. Migrations run per-service (`just migrate` vs `just migrate-content`).
- **Real example:** Adding a "difficulty" field to terms? That's content-service's schema (services/content/alembic/). Game-service just reads it over gRPC.

### 2. gRPC + gRPC Cache + Kafka Events

game-service caches term definitions (from content-service) in memory. Cache has TTL (300s) *and* Kafka listener.

- **Why both?** TTL is the floor (if Kafka is down, stale data is bounded). Events are immediate invalidation.
- **How it works:** Content-service publishes `TermPublished` → Kafka → game-service background task → evicts cache entry. Next player reads fresh term.
- **Cognitive load:** The cache has two paths: time-based (TTL fires) and event-based (Kafka fires). Only one needs to fire.
- **Real example:** Edit a term definition at :8001 → watch game logs for "Invalidated cached term X" within 2s → next player sees fresh definition.

### 3. Deterministic Grading (Same Input = Same Output)

Player submits "Unit of Work" → scores 87 (expansion 28, concept 35, …) → commits. Same player, same answer, same term → always 87, same breakdown. Deterministic.

- **Why?** Cacheable. Learnable. Fair.
- **But term definitions change.** New definition of "Unit of Work" means new correct answer. That's why cache eviction is critical.
- **Gotcha:** If you change grading logic (e.g., fuzzy threshold), old cached grades are stale. Flush Redis + restart game-service.

### 4. Optional Infrastructure (Kafka, LLM, Redis)

No `KAFKA_BROKER_URL` env var? Publisher becomes in-memory no-op. No `ANTHROPIC_API_KEY`? LLM grading disabled. Same pattern everywhere.

- **Why?** Local dev shouldn't require all infra. Cloud deployments can opt in.
- **Real example:** `just dev` without pipeline? Dagster just doesn't run. Without Kafka? Event-driven eviction disabled, TTL is the only cache invalidation.

### 5. Clean Architecture (Framework-Free Domain)

The grading logic lives in `services/game/game_service/domain/grader.py`. No FastAPI. No SQLAlchemy. Pure business logic.

- **Why?** Testable independently. Portable. Durable. Not coupled to web frameworks.
- **How it's enforced:** `import-linter` runs in CI. Tries to import SQLAlchemy in domain? CI fails. Non-negotiable.
- **Real example:** Test grading logic with `pytest` directly on domain classes. No need for FastAPI TestClient or mock DB. Test the logic, not the wiring.

## Common Tasks: Where Code Lives

| Task | File | What It Means |
|------|------|---------------|
| Add a grading path (exact → alias → fuzzy → LLM) | `services/game/.../domain/grader.py` | Pure logic, no frameworks |
| Add a new REST endpoint | `services/game/.../api/routers/answers.py` | FastAPI router, calls use cases |
| Change term schema | `services/content/.../domain/term.py` + Alembic migration | Domain model + DB schema |
| Extract new candidate source | `services/pipeline/.../extractors/new_source.py` | Pure extraction, returns TermCandidate list |
| Store session field | `services/game/.../infrastructure/sql_uow.py` + migration | SQLAlchemy ORM + Alembic |
| Understand why we did X | `docs/adr/000X-*.md` | Decisions, trade-offs, reversibility |

## Action Items (Now)

1. **Run the stack (5 min)**

   ```bash
   just sync && just up && just dev
   # In another terminal: curl localhost:8000/docs
   ```

   Goal: See services start, no errors.

2. **Run tests (2 min)**

   ```bash
   # New terminal (stack still running)
   just test
   ```

   Goal: 400+ tests pass. You didn't break anything.

3. **Read the docs (15 min)**

   - README.md (project scope, phases)
   - docs/adr/0001-*.md, 0003-*.md (why workspace? why clean architecture?)
   - docs/adr/0009-*.md (why gRPC + two services?)

4. **Make a small change (10 min)**

   - Edit `services/game/game_service/domain/grader.py`, add a comment
   - Save → watch auto-reload
   - Run `just test` → confirm still passing
   - Run `just check` → lint + type-check pass
   - Revert the change

5. **Ask a question or pick a small issue**

   - Your first real task: understand one test fully, or add one new test case
   - Run it, see it pass, understand what it proved

## What NOT to Do

| ❌ Don't | ✅ Do | Why |
|----------|-------|-----|
| Import frameworks in domain/ | Keep domain pure | `import-linter` enforces it; CI will reject |
| Add abstractions before 3rd use | Concrete code first | Over-engineering burns time |
| Commit without `just check` | Run checks before staging | Catch issues early |
| Use `git add .` | `git add services/game/...` | Avoid staging unrelated files |
| Hardcode paths in comments | Name the function/class instead | Code moves; paths rot instantly |
| Merge stacked PRs with `--delete-branch` | Merge with plain `gh pr merge --merge` | `--delete-branch` auto-closes dependent PRs |

## Ports & URLs (Quick Reference)

| Service | Port |
| --- | --- |
| game | 8000 |
| content | 8001 |
| pipeline (Dagster) | 3000 |
| web | 5173 |

See [full ports reference](docker-compose-guide.md#ports--urls) for all services including internal ports.

## Next: Deep Dives

- **CLAUDE.md** — Coding standards (ACROSS principles, type hints, commit messages, API contract)
- **docs/game-rules.md** — How scoring works (rubric breakdown, verdicts, grading paths)
- **development.md** — DB migrations, secrets, testing strategy
- **docs/architecture-diagrams.md** — Deployment diagram, Dagster pipeline, caching strategy

---

**Golden rule:** Ship one module at a time, explain the why, ask before big changes. The owner reads every line.
