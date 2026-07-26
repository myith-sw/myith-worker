"""DB 엔진·세션.

오프라인 배치(app/ncs 로더)는 동기 psycopg2로 돈다 — 일회성 실행이라
async가 이득이 없고, Alembic도 동기 드라이버를 쓴다. 런타임 앱의 async
엔진은 이후 메시징 PART에서 별도로 추가한다.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import settings


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
