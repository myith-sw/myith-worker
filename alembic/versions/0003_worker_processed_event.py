"""worker_processed_event: Worker 수신 멱등 테이블 (확정 W2 A-1)

Core 소유 `processed_event`와 별개다 — 같은 DB(myith)를 공유하므로 이름이 겹치면
서로 다른 이벤트의 eventId가 같은 PK 공간에서 충돌한다. C-1(Core 테이블 쓰기 금지)도
지킨다.

Revision ID: 0003_worker_processed_event
Revises: 0002_worker_owned_tables
Create Date: 2026-07-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_worker_processed_event"
down_revision: Union[str, None] = "0002_worker_owned_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "worker_processed_event",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "consumed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("worker_processed_event")
