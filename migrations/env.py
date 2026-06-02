from logging.config import fileConfig
import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from config.load_env import load_env_file
from config.settings import DEFAULT_DATABASE_URL
from db.base import Base
import db.models


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

load_env_file()
config.set_main_option('sqlalchemy.url', os.getenv('DATABASE_URL', DEFAULT_DATABASE_URL))

target_metadata = Base.metadata


def include_object(object_, name, type_, reflected, compare_to):
    if type_ == 'index' and name == 'ix_leaderboard_entries_tournament_total_points':
        return False
    return True


def run_migrations_offline():
    url = config.get_main_option('sqlalchemy.url')
    context.configure(
        url=url,
        target_metadata=target_metadata,
        include_object=include_object,
        literal_binds=True,
        dialect_opts={'paramstyle': 'named'},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix='sqlalchemy.',
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, include_object=include_object)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
