# Monolith build: one image holds every workspace member. Only one service
# (game) exists today, so CMD runs it directly. Splitting into per-service
# images stays a one-file change once a second service exists (ADR-0006).

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
COPY services/content/pyproject.toml services/content/
COPY libs/core/pyproject.toml libs/core/

COPY services/ services/
COPY libs/ libs/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --all-packages

FROM python:3.14-slim-trixie AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

RUN groupadd --system app && useradd --system --gid app --no-create-home app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/services/game:/app/services/content" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /app/services /app/services
COPY --from=builder --chown=app:app /app/libs /app/libs
COPY --chown=app:app alembic.ini /app/
COPY --chown=app:app alembic-content.ini /app/

WORKDIR /app

USER app
EXPOSE 8000
EXPOSE 8001

# 12-factor app: same binary everywhere. PROCESS_TYPE env var determines
# behavior. CMD defaults to game-service; compose overrides it for content
# (ADR-0006: one image, command-selected service).
CMD ["python", "services/game/game_service/bin/run.py"]
