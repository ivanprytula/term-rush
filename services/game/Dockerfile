# Monolith build: one image holds every workspace member. Only one service
# (game) exists today, so CMD runs it directly — see ADR-0007 on why services
# aren't namespaced yet. Splitting into per-service images stays a one-file
# change once a second service exists.

FROM python:3.14-slim-trixie AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
		PYTHONUNBUFFERED=1

# Install uv
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#installing-uv
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /uvx /bin/

WORKDIR /app/

# Place executables in the environment at the front of the path
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#using-the-environment
ENV PATH="/app/.venv/bin:$PATH"

RUN --mount=type=cache,target=/root/.cache/uv \
		--mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --no-install-workspace --all-packages

# Dependencies resolve from the lockfile alone, so this layer survives any
# source edit. --no-install-workspace keeps our own packages out of it.
COPY pyproject.toml uv.lock ./

COPY services/game/pyproject.toml services/game/

COPY services/ services/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --all-packages

FROM python:3.14-slim-trixie AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

RUN groupadd --system app && useradd --system --gid app --no-create-home app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/services/game" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /app/services /app/services
COPY --chown=app:app alembic.ini /app/
COPY --chown=app:app services/game/alembic/ /app/alembic/

WORKDIR /app/services/game

USER app
EXPOSE 8000

# 12-factor app: same binary everywhere. PROCESS_TYPE env var determines behavior.
CMD ["python", "bin/run.py"]
