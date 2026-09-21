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
    uv run ty check services/content

precommit:
    uv run prek run --all-files

# Regenerate gRPC stubs from term.proto (commit the result; not built at image build time).
proto:
    #!/usr/bin/env bash
    set -euo pipefail
    cd libs/term-proto
    uv run python -m grpc_tools.protoc \
        --proto_path=proto \
        --python_out=src/term_proto \
        --grpc_python_out=src/term_proto \
        --pyi_out=src/term_proto \
        proto/term.proto
    sed -i 's/^import term_pb2 as term__pb2$/from term_proto import term_pb2 as term__pb2/' src/term_proto/term_pb2_grpc.py

# Architecture contracts: layering, framework-free domain, service isolation
# --no-cache: import-linter's cache_dir isn't a pyproject.toml option (only a
# CLI flag) — without --no-cache it caches to services/*/.import_linter_cache/
# by default, which arch-verify's mutate-then-restore dance can leave stale.
arch:
    cd services/game && uv run lint-imports --no-cache
    cd services/content && uv run lint-imports --no-cache

# Prove the architecture contracts actually fail on a violation.
arch-verify:
    #!/usr/bin/env bash
    set -uo pipefail
    f=services/game/game_service/domain/term.py
    cp "$f" "$f.bak"
    echo 'import sqlalchemy' >> "$f"
    cd services/game && uv run lint-imports --no-cache > /dev/null 2>&1
    rc=$?
    cd - > /dev/null
    mv "$f.bak" "$f"
    if [ $rc -eq 0 ]; then
        echo "FAIL: domain imported sqlalchemy and the contract did not catch it"
        exit 1
    fi
    echo "OK: architecture contracts reject a domain->framework import"

# Prove the service-isolation contract actually fails on a violation.
arch-verify-service-isolation:
    #!/usr/bin/env bash
    set -uo pipefail
    f=services/game/game_service/infrastructure/grpc_term_repository.py
    cp "$f" "$f.bak"
    echo 'import content_service' >> "$f"
    cd services/game && uv run lint-imports --no-cache > /dev/null 2>&1
    rc=$?
    cd - > /dev/null
    mv "$f.bak" "$f"
    if [ $rc -eq 0 ]; then
        echo "FAIL: game_service imported content_service and the contract did not catch it"
        exit 1
    fi
    echo "OK: architecture contracts reject a game_service->content_service import"

check: quality arch test test-content

# === Tests ===

# Game service + libs tests (default scope; pass a path to narrow further).
test *ARGS:
    uv run pytest {{ARGS}}

# Content service tests (separate scope: own pyproject.toml, no cross-service collection).
test-content *ARGS:
    cd services/content && uv run pytest {{ARGS}}

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

# Start postgres, postgres-content, redis, and redpanda for local development.
up:
    docker compose up -d --wait postgres postgres-content redis redpanda
    @echo "postgres: localhost:5432"
    @echo "postgres-content: localhost:5433"
    @echo "redis: localhost:6379"
    @echo "redpanda: localhost:9092"

# Stop postgres, postgres-content, redis, and redpanda.
down:
    docker compose down

# Run game-service database migrations.
migrate:
    #!/usr/bin/env bash
    export PYTHONPATH=services/game
    export PROCESS_TYPE=migrate
    export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/term_rush
    uv run python services/game/game_service/bin/run.py

# Run content-service database migrations.
migrate-content:
    #!/usr/bin/env bash
    export PYTHONPATH=services/content
    export PROCESS_TYPE=migrate
    export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/term_rush_content
    uv run python services/content/content_service/bin/run.py

# Seed content-service's term bank (requires postgres-content + migrations run first).
seed-content:
    #!/usr/bin/env bash
    export PYTHONPATH=services/content
    export PROCESS_TYPE=seed
    export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/term_rush_content
    uv run python services/content/content_service/bin/run.py

# Run game-service API with hot-reload (:8000; requires postgres + migrations + content-service running).
dev:
    #!/usr/bin/env bash
    export PYTHONPATH=services/game
    export PROCESS_TYPE=api
    export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/term_rush
    export REDIS_URL=redis://localhost:6379/0
    export CONTENT_SERVICE_GRPC_URL=localhost:50051
    export ENVIRONMENT=development
    uv run python services/game/game_service/bin/run.py

# Run content-service API with hot-reload (:8001 REST, :50051 gRPC; requires postgres-content + migrations).
dev-content:
    #!/usr/bin/env bash
    export PYTHONPATH=services/content
    export PROCESS_TYPE=api
    export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/term_rush_content
    export ENVIRONMENT=development
    uv run python services/content/content_service/bin/run.py

# Run content-service then game-service, both with hot-reload (content-service first: game-service's gRPC calls need it up).
dev-all:
    #!/usr/bin/env bash
    set -euo pipefail
    trap 'kill 0' EXIT
    just dev-content &
    sleep 2
    just dev

# Full local stack from cold: infra containers (up), both services'
# migrations, content-service seed data, then both APIs with hot-reload.
# Ctrl-C stops the APIs; the containers from `up` keep running — `just down`
# to stop those too.
run-all: up
    just migrate
    just migrate-content
    just seed-content
    just dev-all

# Run the Vite dev server (proxies /game-rounds and /terms to dev on :8000).
web port="5173":
    cd services/web && npm run dev -- --port {{port}}

# Regenerate services/web's TS client from game-service's live OpenAPI schema.
# Commit the result; CI's web-client-drift job fails if it's out of sync.
generate-client:
    #!/usr/bin/env bash
    set -euo pipefail
    PYTHONPATH=services/game uv run python -c \
        "from game_service.api.app import app; import json; print(json.dumps(app.openapi()))" \
        > services/web/openapi.json
    cd services/web && npm run generate-client

# Playwright browser UI tests (mocked backend, not full-stack e2e — no
# game-service/Postgres needed; see services/web/README.md).
web-test-ui:
    cd services/web && npm run test:ui

# Interactive web UI to browse content-service's gRPC contract and fire test calls.
# brew install grpcurl grpcui   # or: go install github.com/fullstorydev/grpcurl/cmd/grpcurl@latest
# # list services
#grpcurl -plaintext -import-path libs/term-proto/proto -proto term.proto localhost:50051 list

# call GetById
#grpcurl -plaintext -import-path libs/term-proto/proto -proto term.proto \
#  -d '{"term_id": "outbox-pattern"}' \
#  localhost:50051 termrush.content.v1.TermService/GetById

# call GetRandom
#grpcurl -plaintext -import-path libs/term-proto/proto -proto term.proto \
#  -d '{}' localhost:50051 termrush.content.v1.TermService/GetRandom
grpc-ui addr="localhost:50051":
    grpcui -plaintext -import-path libs/term-proto/proto -proto term.proto {{addr}}

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
