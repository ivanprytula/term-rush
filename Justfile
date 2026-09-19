set shell := ["bash", "-uc"]

default:
    @just --list

# === Setup & Code Quality ===

# Install the workspace (creates .venv at the root)
sync:
    uv sync --all-packages

quality:
    uv run ruff check .
    uv run ruff format .
    uv run ty check services/game

precommit:
    uv run prek run --all-files

# Architecture contracts: layering, framework-free domain, service isolation
arch:
    cd services/game && uv run lint-imports

# Prove the architecture contracts actually fail on a violation.
arch-verify:
    #!/usr/bin/env bash
    set -uo pipefail
    f=services/game/domain/term.py
    cp "$f" "$f.bak"
    echo 'import sqlalchemy' >> "$f"
    cd services/game && uv run lint-imports > /dev/null 2>&1
    rc=$?
    cd - > /dev/null
    mv "$f.bak" "$f"
    if [ $rc -eq 0 ]; then
        echo "FAIL: domain imported sqlalchemy and the contract did not catch it"
        exit 1
    fi
    echo "OK: architecture contracts reject a domain->framework import"

check: quality arch test

# === Tests ===

test *ARGS:
    uv run pytest {{ARGS}}

coverage:
    uv run pytest --cov-report=term-missing:skip-covered
    @echo "HTML report: coverage/index.html"

# === Utilities ===

shell:
    cd services/game && uv run python

clean:
    find . -name '__pycache__' -type d -not -path './.venv/*' -exec rm -rf {} + 2>/dev/null || true
    rm -rf .cache coverage .coverage

# === Running Services & Containers ===

# Start postgres and redis for local development.
up:
    docker compose up -d postgres redis
    @echo "postgres: localhost:5432"
    @echo "redis: localhost:6379"

# Stop postgres and redis.
down:
    docker compose down

# Run database migrations.
migrate:
    #!/usr/bin/env bash
    export PYTHONPATH=services/game
    export PROCESS_TYPE=migrate
    export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/term_rush
    uv run python services/game/bin/run.py

# Seed the terms table with sample data (requires postgres + migrations run first).
seed:
    #!/usr/bin/env bash
    export PYTHONPATH=services/game
    export PROCESS_TYPE=seed
    export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/term_rush
    uv run python services/game/bin/run.py

# Run API server with hot-reload (always on :8000; requires postgres + migrations run first).
dev:
    #!/usr/bin/env bash
    export PYTHONPATH=services/game
    export PROCESS_TYPE=api
    export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/term_rush
    export REDIS_URL=redis://localhost:6379/0
    export ENVIRONMENT=development
    uv run python services/game/bin/run.py

# Run the Vite dev server (proxies /sessions and /terms to dev on :8000).
web port="5173":
    cd services/web && npm run dev -- --port {{port}}

# === Smoke Tests ===

smoke:
    #!/usr/bin/env bash
    set -euo pipefail
    IMAGE="term-rush:smoke"
    docker build -f services/game/Dockerfile -t "$IMAGE" .
    cid=$(docker run -d -p 8000:8000 "$IMAGE")
    trap 'docker rm -f "$cid" > /dev/null' EXIT
    for _ in $(seq 30); do
        curl -sf localhost:8000/health > /dev/null && break
        sleep 1
    done
    curl -sf localhost:8000/health | tee /dev/stderr | grep -q '"ok"'
    curl -sf localhost:8000/ready  | tee /dev/stderr | grep -q '"ready"'
    echo "OK: image serves /health and /ready"
