"""ncs_load_cursor: NCS 오프라인 배치 재개 커서 (확정 W2 D-3)

자격종목 API는 1,000건/일. 능력단위마다 API 호출 → upsert → 커서 갱신 → 매 건 커밋.
쿼터 초과 시 커서를 남기고 정상 종료, 재실행 시 이어서 적재한다.

Revision ID: 0005_ncs_load_cursor
Revises: 0004_job_ncs_detail_code
Create Date: 2026-07-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_ncs_load_cursor"
down_revision: Union[str, None] = "0004_job_ncs_detail_code"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ncs_load_cursor",
        sa.Column("loader_name", sa.String(), primary_key=True),  # 'certification'
        sa.Column("last_unit_code", sa.String(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("ncs_load_cursor")
