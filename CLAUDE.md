# Term Rush — working agreement

## The owner reads every line

This is a portfolio project whose purpose is that the owner genuinely knows his own
codebase and can defend any line of it in an interview. Code he cannot account for is
worse than no code.

**Therefore, for any agent working here:**

- Ship **one module or concept at a time**, then stop for review. Never dump many files
  in a single turn.
- Prefer boring, explicit code. Cleverness that needs decoding is a liability.
- Flag anything deserving extra scrutiny: subtle logic, edge cases, places you were
  uncertain or got something wrong.
- Do not commit unless asked. The owner tests and verifies himself.

## Be terse

Verbose prose costs the reader attention. Density is a feature.

- **Comments only where the code cannot speak.** A non-obvious decision, a magic
  constant's origin, a deliberate trade-off. Never restate what the line does.
- **Docstrings: one line.** Extend only for genuinely non-obvious contracts or units.
  No Args/Returns blocks that repeat the type signature.
- **No section-header comments** (`# --- helpers ---`), no banner art, no narration.
- **Commit messages:** subject line, plus body only when the *why* isn't evident.
  No bullet summaries of the diff - the diff is the summary.
- **PR bodies:** what changed, why, how to verify. Three short sections maximum.
- **Chat replies:** lead with the answer. Skip preamble, skip recap of what was just read, skip closing summaries that repeat the body.

ADRs are the deliberate exception - they carry reasoning, and reasoning is their point. Keep them structured and skimmable, not chatty.

## Design Principles

Follow ACROSS (see `~/.claude/CLAUDE.md` for the full rule set: Abstractions - Decomposition, Composition by
Default, escape the Rabbit hole, Optimize for change, Simple as possible, Screaming contract).

## Git Workflow

- Branch from `main` as `feature/<name>`. Never commit directly to `main`.
- Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `refactor:`, `chore:`).
- Stage changes for review. Do not commit or push unless asked.
- No `Co-Authored-By:` trailers or tool-attribution lines in commits or PR bodies.

## Code Style

- Follow existing FastAPI patterns in `services/game/api/app.py`
- **FastAPI Annotated style:** Use `Annotated[Type, Depends(...)]` for dependencies; creates reusable type aliases (e.g., `SessionTokenDep = Annotated[TokenPayload, Depends(...)]`). Path parameters use `Annotated[str, Path(...)]` to validate at the API boundary.
- Use `ruff` for linting and formatting (config in `pyproject.toml`: auto-fix, line-length 88, import sorting)
- Use `ty` for type checking
- Type-hint every public function and method, including return types
- Write Google-style docstrings for every public function and method
- Use `pathlib` for filesystem paths - never `os.path`
- Prefer f-strings over `str.format()` or `%` formatting
- Follow EAFP: handle the exception rather than pre-checking the condition
- Validate request bodies with Pydantic models
- Prefer idiomatic Python: comprehensions, generators, decorators, context managers
- **Avoid hardcoding file paths or line numbers in comments, docstrings, and docs.**
  A path reference goes stale the moment code moves. Name the function/class instead
  (e.g., "see `rubric_scorer` module", not "see `services/game/domain/rubric_scorer.py:15`").
- **Don't name a module inside its own docstring.** The file already states its name;
  describe what it does. Refer to other code by the class/function it exports.

## Architecture invariants — machine-enforced

`import-linter` contracts in `services/game/pyproject.toml` enforce these:

1. **Layering:** `api - infrastructure - application - domain`. Never the reverse.
2. **The domain is framework-free.** `domain/` must not import `fastapi`, `sqlalchemy`,
   `redis` or `celery`. Principles live in `domain/`; frameworks are quarantined in
   `infrastructure/`. See [ADR-0003](docs/adr/0003-principles-before-frameworks.md).
3. **Service isolation: deferred.** See [ADR-0007](docs/adr/0007-flat-service-layout.md)
   on why per-service namespaces don't exist yet.

Run before claiming anything works: `just check` (from the repo root).

## Code Conventions

- **Domain language in names.** `SubmitAnswer`, `GradeOutcome`, `TermPerformance` - not `process_answer()`, generic `Handler`, or `True`/`False` return values.
- **Typed results over bools.** The caller must know *why* without catching exceptions or parsing strings: `GradeOutcome(verdict, rubric, matched_via, ...)`.
- **Frozen pydantic models** for domain entities and value objects.
- **Tests pin behaviour, not implementation.** The original prototype's `similarity()` function runs as an oracle so regressions surface immediately.
- **REST endpoints speak domain language:** `POST /sessions/{id}/answers/submit`, not `/api/process`. Status codes are meaningful: 422 for validation errors, 401/403 for auth, never 400 for everything.
- **Constants in one place.** All magic numbers (rubric weights, string bounds, thresholds) live in `domain/constants.py`. Changes to a bound propagate everywhere: domain validation, API schemas, tests. Repeat a constant in CLAUDE.md for QA reference (e.g., "score 0-100") but source-of-truth is always `constants.py`.

## API Contract for QA & Test Automation

**Endpoint:** `POST /sessions/{session_id}/answers/submit`

**Request:**

- `term_id` (string, 1-64 chars): the term being answered
- `answer` (string, 1-512 chars): the student's explanation

**Response (200):**

- `verdict` (enum): one of `correct`, `partial`, `incorrect`
- `matched_via` (enum): grading path: `exact`, `alias`, `fuzzy`, `llm_rubric`
- `confidence` (float, 0.0-1.0): certainty of the match (exact=1.0, fuzzy~0.5)
- `score` (int, 0-100): sum of rubric components
- `feedback` (string): localized explanation for the student
- `rubric` (object):
  - `expansion` (0-30): term definition score
  - `concept` (0-40): core understanding score
  - `purpose` (0-20): use case / benefit score
  - `example` (0-10): illustration / analogy score
  - `total` (0-100): sum

**Error responses:**

- `422`: validation error (invalid term_id/answer length)
- `404`: term not found (ValueError raised by use case)
- `500`: internal error (unexpected exception)

**Determinism & caching:** Identical answers always return the same outcome (in-memory cache Phase 1).

## Input Validation & Security

- Request bodies validated with Pydantic models before business logic runs.
- No credentials passed as CLI args or shell env vars; use `.env` (gitignored) or
  Secret Manager.
- Database errors logged server-side only; clients get generic 5xx.
- Sensitive data (passwords, tokens, keys, email) never logged.
- Error messages are generic: `"Answer evaluation failed"`, not `str(exc)`.

## Documentation

Every significant decision gets an ADR in `docs/adr/`, including a **"When I would
change this"** section. An ADR without a stated reversal condition is an advertisement,
not a decision record. `docs/skills-map.md` tracks capability coverage honestly,
including deliberate omissions.

**Markdown files:** Always specify the language in fenced code blocks (` ```text`, ` ```bash`,
` ```python`, ` ```json`, etc.). This enables proper syntax highlighting and linting.
**List formatting (MD032):** Surround lists with blank lines - never place a list immediately after prose (e.g., `text:` must have a blank line before the first `- item`). This applies to all `.md` files including ADRs.

## Debugging & Verification

After making a change:

1. `just check` - ruff + ty + import-linter + pytest all pass
2. Run affected tests: `just test services/game/tests/unit/test_domain.py` (for domain changes)
3. Check error messages: grep for generic wording, no info leaks (no paths, env vars, schemas)
4. Rebuild image locally: `just smoke` (builds, starts, probes /health, tears down)
5. **Markdown files:** Run `uv run mdlint check .` before committing any `.md` file - fixes MD032 (blank lines around lists), MD040 (fenced code block language), and MD013 (line length <=80). Applies to docs/, README.md, CLAUDE.md, development.md, and all ADRs.

## Workspace Structure

```text
services/game/
  domain/           # Entities, value objects, graders (framework-free)
  application/      # Use cases, Ports (Protocols)
  infrastructure/   # Adapters (in-memory, SQLAlchemy, Redis, etc.)
  api/              # FastAPI routers, dependency injection
  tests/
    unit/           # Domain and use-case tests
    integration/    # API and adapter tests (FastAPI TestClient)
  pyproject.toml    # Game service package config
  Dockerfile        # Monolith image (builds entire workspace)

libs/core/
  src/termrush_core/
    events.py       # Domain event envelope (cross-service)
  pyproject.toml    # Shared library config

docs/
  adr/              # Architectural Decision Records
  skills-map.md     # Capability coverage (Covered/Partial/Planned/Deferred/Skipped)
  development.md    # Development guide

Root:
  pyproject.toml    # Workspace config, tool settings (ruff, ty, pytest, coverage)
  Justfile          # Task automation (sync, test, quality, arch, check, build, run, smoke, clean, coverage)
  compose.yml       # Local dev stack (planned: postgres, redis, api, web)
  .pre-commit-config.yaml  # Pre-commit hooks (prek)
```

## Justfile Commands

- `just sync` - Install workspace (uv sync --all-packages)
- `just test [ARGS]` - Run pytest with optional args
- `just coverage` - Run tests with coverage report (HTML + terminal)
- `just quality` - Lint + format (ruff) + type-check (ty)
- `just arch` - Verify import-linter contracts
- `just arch-verify` - Prove contracts fail on violation (negative test)
- `just check` - quality + arch + test (full gate)
- `just build` - Docker build (monolith image)
- `just run [port]` - Run API container (default 8000)
- `just smoke` - Build, start, probe /health and /ready, tear down
- `just clean` - Remove `__pycache__`, `.cache`, coverage artifacts
- `just precommit` - Run pre-commit hooks (prek run --all-files)
