"""Alembic environment.

The database URL and the metadata come from the application, not from
`alembic.ini`, so `alembic upgrade head` on the command line and the
automatic upgrade at startup can never disagree about which database they
are talking to. The URL in `alembic.ini` is a placeholder and is ignored.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# The API package root, so `app` imports resolve wherever alembic is run
# from: the CLI, a container entrypoint, or the app itself at startup.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import Base, database_url  # noqa: E402

config = context.config

# Only configure logging for a standalone run. When the app drives the
# upgrade at startup it has already set up logging, and re-reading the ini
# file here would silently replace the application's handlers.
if config.config_file_name is not None and config.attributes.get("standalone", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Escaped because ConfigParser treats `%` as interpolation syntax, and a
# password or path containing one would otherwise raise here.
config.set_main_option("sqlalchemy.url", database_url().replace("%", "%%"))


def include_object(_object, name, type_, _reflected, _compare_to) -> bool:
    """Keep alembic's own bookkeeping table out of autogenerate."""
    return not (type_ == "table" and name == "alembic_version")


#: SQLite cannot ALTER a column in place; batch mode rebuilds the table
#: around the change instead. Without it every migration that is not a plain
#: ADD COLUMN fails on the database this project actually runs on.
_OPTIONS = {
    "target_metadata": target_metadata,
    "render_as_batch": True,
    "compare_type": True,
    "include_object": include_object,
}


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **_OPTIONS,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run(connection) -> None:
    context.configure(connection=connection, **_OPTIONS)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # A connection supplied by the caller (the startup path) wins, so
    # migrations run on the caller's connection rather than opening a second
    # one against the same SQLite file.
    existing = config.attributes.get("connection")
    if existing is not None:
        _run(existing)
        return

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        _run(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
