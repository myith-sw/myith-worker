"""DB 엔진·세션.

오프라인 배치(app/ncs 로더)는 동기 psycopg2로 돈다 — 일회성 실행이라
async가 이득이 없고, Alembic도 동기 드라이버를 쓴다.

런타임 앱(메시징 컨슈머의 멱등 INSERT)은 async 엔진을 쓴다 — get_async_sessionmaker().
DATABASE_URL이 없으면 None을 돌려주고, 호출부는 멱등을 건너뛴다(기동은 성공, O-3).
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker as _AsyncSessionmaker


def _sync_url() -> str:
    url = settings.DATABASE_URL
    if not url:
        raise RuntimeError(
            "DATABASE_URL이 없다. 배치 적재는 DB가 필요하다. "
            "docker compose run 시 환경변수로 주입한다 (O-3)."
        )
    # async 드라이버가 들어와도 배치는 동기 드라이버로 돌린다.
    return url.replace("postgresql+asyncpg://", "postgresql://")


def make_engine() -> Engine:
    return create_engine(_sync_url(), pool_pre_ping=True, future=True)


@contextmanager
def session_scope() -> Iterator[Session]:
    """트랜잭션 경계. 성공 시 커밋, 예외 시 롤백."""
    engine = make_engine()
    factory = sessionmaker(bind=engine, future=True)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


# ── 런타임 앱용 async 엔진 (컨슈머 멱등 INSERT). 프로세스당 1회 생성해 재사용. ──
_async_factory: "_AsyncSessionmaker | None" = None


def get_async_sessionmaker() -> "_AsyncSessionmaker | None":
    """async 세션 팩토리. DATABASE_URL이 없으면 None(호출부는 멱등을 건너뛴다)."""
    global _async_factory
    if _async_factory is not None:
        return _async_factory
    url = settings.async_database_url
    if not url:
        return None
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(url, pool_pre_ping=True)
    _async_factory = async_sessionmaker(engine, expire_on_commit=False)
    return _async_factory
