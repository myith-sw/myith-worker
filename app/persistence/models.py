"""SQLAlchemy 선언적 Base.

Worker 소유 테이블만 여기 정의한다 (C-1, PART E). Core 소유 테이블의
DDL은 여기 넣지 않는다. 실제 모델은 이후 PART에서 추가한다. 지금은 Alembic
autogenerate가 참조할 빈 메타데이터만 노출한다.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
