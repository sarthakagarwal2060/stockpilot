from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

from app import models  # noqa: F401 - registers tables on Base.metadata
from app.config import settings
from app.db import Base

config = context.config
# configparser treats "%" as interpolation, and URL-encoded passwords contain "%".
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata

# Every backend replica runs `alembic upgrade head` on start; this lock makes them take turns.
MIGRATION_LOCK_ID = 74_210_001


def run_migrations_offline():
    context.configure(url=settings.database_url, target_metadata=target_metadata, literal_binds=True,
                      dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(config.get_section(config.config_ini_section), prefix="sqlalchemy.",
                                     poolclass=pool.NullPool)
    with connectable.connect() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_lock(:id)"), {"id": MIGRATION_LOCK_ID})
            connection.commit()  # session-level lock survives; released when the connection closes
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
