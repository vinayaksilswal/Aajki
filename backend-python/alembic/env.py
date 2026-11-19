from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

import app.models  # noqa: F401  (registers every table)
from app.db import Base, database_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

# Prototype tables kept in the database (not dropped without a deliberate decision) but no
# longer mapped by the app. Excluded from autogenerate so `alembic check` stays a clean gate.
RETAINED_UNMAPPED = {"stories", "boards", "settings"}


def include_object(obj, name, type_, reflected, compare_to):
    return not (type_ == "table" and reflected and name in RETAINED_UNMAPPED)


def run_migrations_offline() -> None:
    context.configure(url=database_url(), target_metadata=target_metadata, literal_binds=True,
                      render_as_batch=True, include_object=include_object)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = database_url()
    connectable = config.attributes.get("connection")
    if connectable is None:
        engine = create_engine(url, poolclass=pool.NullPool)
        with engine.connect() as connection:
            _run(connection, url)
    else:
        _run(connectable, url)


def _run(connection, url: str) -> None:
    # SQLite can't ALTER most things in place; batch mode rebuilds tables when needed.
    context.configure(connection=connection, target_metadata=target_metadata,
                      render_as_batch=url.startswith("sqlite"), include_object=include_object)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
