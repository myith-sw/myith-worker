"""ncs offline batch tables: ncs_unit, ncs_certification, skill_ncs_map

오프라인 배치 소유 테이블 (C-1, PART E). Core 소유 테이블은 여기서 다루지 않는다.

Revision ID: 0001_ncs_offline_tables
Revises:
Create Date: 2026-07-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_ncs_offline_tables"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ncs_unit",
        sa.Column("code", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("major_name", sa.String(), nullable=True),
        sa.Column("middle_name", sa.String(), nullable=True),
        sa.Column("minor_name", sa.String(), nullable=True),
        sa.Column("detail_name", sa.String(), nullable=True),
    )
    op.create_table(
        "ncs_certification",
        sa.Column(
            "ncs_unit_code",
            sa.String(),
            sa.ForeignKey("ncs_unit.code"),
            primary_key=True,
        ),
        sa.Column("cert_code", sa.String(), primary_key=True),
        sa.Column("cert_name", sa.String(), nullable=False),
        sa.Column("unit_type", sa.String(), nullable=True),
    )
    op.create_table(
        "skill_ncs_map",
        sa.Column("skill_code", sa.String(), primary_key=True),
        sa.Column(
            "ncs_unit_code",
            sa.String(),
            sa.ForeignKey("ncs_unit.code"),
            primary_key=True,
        ),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_table("skill_ncs_map")
    op.drop_table("ncs_certification")
    op.drop_table("ncs_unit")
