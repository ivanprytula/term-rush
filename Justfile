set shell := ["bash", "-uc"]

default:
    @just --list

# Install the workspace (creates .venv at the root)
sync:
    uv sync --all-packages

test *ARGS:
    uv run pytest {{ARGS}}

coverage:
    uv run pytest --cov-report=term-missing:skip-covered
    @echo "HTML report: coverage/index.html"

quality:
    uv run ruff check .
    uv run ruff format .
    uv run ty check services/game

precommit:
    uv run prek run --all-files

# Architecture contracts: layering, framework-free domain, service isolation
arch:
    cd services/game && uv run lint-imports

check: quality arch test

# Prove the architecture contracts actually fail on a violation.
# A rule that never fails is decorative.
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

IMAGE := "term-rush"

build:
    docker build -f services/game/Dockerfile -t {{IMAGE}}:dev .

# Run the game-service from the monolith image.
run port="8000":
    docker run --rm -p {{port}}:8000 {{IMAGE}}:dev

# Build, start, probe /health and /ready, tear down.
smoke: build
    #!/usr/bin/env bash
    set -euo pipefail
    cid=$(docker run -d -p 8000:8000 {{IMAGE}}:dev)
    trap 'docker rm -f "$cid" > /dev/null' EXIT
    for _ in $(seq 30); do
        curl -sf localhost:8000/health > /dev/null && break
        sleep 1
    done
    curl -sf localhost:8000/health | tee /dev/stderr | grep -q '"ok"'
    curl -sf localhost:8000/ready  | tee /dev/stderr | grep -q '"ready"'
    echo "OK: image serves /health and /ready"

clean:
    find . -name '__pycache__' -type d -not -path './.venv/*' -exec rm -rf {} + 2>/dev/null || true
    rm -rf .cache coverage .coverage
