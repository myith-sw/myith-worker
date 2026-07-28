"""user_quest_guidance: 층2 퀘스트 문구 개인화 (확정 W-H1-C, H-1)

Worker 소유·쓰기 / Core 조립 시 읽기(C-1). user_competency와 같은 패턴 —
Core가 조립 시점에 (roadmap_id, skill_code)로 읽어 층1 위에 덮는다. 비어 있으면 층1 폴백.

Revision ID: 0006_user_quest_guidance
Revises: 0005_ncs_load_cursor
Create Date: 2026-07-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_user_quest_guidance"
down_revision: Union[str, None] = "0005_ncs_load_cursor"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_quest_guidance",
        sa.Column("roadmap_id", sa.BigInteger(), primary_key=True),
        sa.Column("skill_code", sa.String(), primary_key=True),
        sa.Column("guidance", sa.Text(), nullable=False),
        sa.Column("tier", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("user_quest_guidance")
