#!/usr/bin/env python3
"""12-factor app entry point: one binary, behavior determined by $PROCESS_TYPE env var.

Runs same code everywhere (local, Docker, Kubernetes) with config via environment.
Migrations and API are separate processes in the process model.
"""

import os
import subprocess
import sys
from pathlib import Path

import uvicorn

from api.config import settings

ROOT = Path(__file__).parent.parent.parent.parent


def run_migrations() -> int:
    """Run Alembic migrations. Returns exit code."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(ROOT / "alembic.ini"),
            "upgrade",
            "head",
        ],
        cwd=str(ROOT),
    )
    return result.returncode


def run_seed() -> None:
    """Seed the terms table with sample data."""
    import asyncio

    from bin.seed import seed

    asyncio.run(seed())


def run_api() -> None:
    """Start the FastAPI server."""
    uvicorn.run(
        "api.app:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.ENVIRONMENT == "development",
    )


def main() -> None:
    """Dispatch based on PROCESS_TYPE env var."""
    process_type = os.getenv("PROCESS_TYPE", "api").lower()

    if process_type == "migrate":
        exit_code = run_migrations()
        sys.exit(exit_code)
    elif process_type == "seed":
        run_seed()
    elif process_type == "api":
        run_api()
    else:
        raise ValueError(
            f"Unknown PROCESS_TYPE: {process_type}. "
            "Must be 'migrate', 'seed', or 'api'."
        )


if __name__ == "__main__":
    main()
