from logging.config import fileConfig
import os
from pathlib import Path
import sys

# Alembic executes this file directly, rather than through pytest's configured
# import path. Keep `alembic current` and `alembic upgrade head` usable from
# backend/ without requiring every developer to export PYTHONPATH manually.
BACKEND_ROOT = str(Path(__file__).resolve().parents[1])
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from alembic import context
from sqlalchemy import engine_from_config, pool
from app.database.session import Base
import app.models
config = context.config
if database_url := os.getenv("DATABASE_URL"):
    config.set_main_option("sqlalchemy.url", database_url)
if config.config_file_name:
    # This project intentionally keeps alembic.ini minimal.  Logging sections
    # are optional and must not prevent schema migrations from running.
    try:
        fileConfig(config.config_file_name)
    except KeyError:
        pass
target_metadata = Base.metadata
def run_migrations_offline():
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction(): context.run_migrations()
def run_migrations_online():
    connectable=engine_from_config(config.get_section(config.config_ini_section, {}),prefix="sqlalchemy.",poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection,target_metadata=target_metadata)
        with context.begin_transaction(): context.run_migrations()
if context.is_offline_mode(): run_migrations_offline()
else: run_migrations_online()
