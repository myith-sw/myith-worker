"""job.ncs_detail_code: 직무 ↔ NCS 세분류 연결 (확정 W2 C-6)

backend·frontend → '20010202'. 나머지는 NULL. 정보보호·마케팅 세분류 확장 대비.

Revision ID: 0004_job_ncs_detail_code
Revises: 0003_worker_processed_event
Create Date: 2026-07-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_job_ncs_detail_code"
down_revision: Union[str, None] = "0003_worker_processed_event"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("job", sa.Column("ncs_detail_code", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("job", "ncs_detail_code")
