"""Alembic 환경. URL은 settings에서 받는다 (C-6). 동기 드라이버(psycopg2)로
마이그레이션을 돌린다 — async 드라이버는 런타임 앱용이다.

Worker 소유 테이블만 다룬다 (C-1). Core의 flyway_schema_history를 건드리지 않는다 (E).
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config.settings import settings
from app.persistence.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _sync_url() -> str:
    url = settings.DATABASE_URL
    if not url:
        raise RuntimeError(
            "DATABASE_URL이 없다. 마이그레이션은 DB가 필요하다. "
            "런타임 컨테이너 기동과 달리 이 명령은 DB 없이는 의미가 없다."
        )
    # async 드라이버가 들어와도 마이그레이션은 동기 드라이버로 돌린다.
    return url.replace("postgresql+asyncpg://", "postgresql://")


def run_migrations_offline() -> None:
    context.configure(
        url=_sync_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _sync_url()
    connectable = engine_from_config(
        section, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
