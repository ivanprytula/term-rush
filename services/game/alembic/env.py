"""Sync Alembic environment for migrations.

This is used for running migrations via alembic CLI.
Adapted from the async template to run synchronously.
"""

from alembic import context
from sqlalchemy import engine_from_config
from sqlalchemy import pool
import os

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    from logging.config import fileConfig
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from game_service.infrastructure.database import Base

# Import all models so they register with Base.metadata
# autogenerate will only detect tables that are imported
import game_service.infrastructure.database  # noqa: F401 - registers Base

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    assert url is not None  # Alembic guarantees sqlalchemy.url is configured
    # Convert asyncpg URL to sync psycopg2
    url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    configuration = config.get_section(config.config_ini_section)
    assert configuration is not None  # Alembic guarantees config section exists
    # Convert asyncpg URL to sync psycopg2 for Alembic CLI
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        db_url = db_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
        configuration["sqlalchemy.url"] = db_url

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.StaticPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
