"""worker owned tables: job, job_profile + runtime tables + ncs_unit.is_verified

이 저장소 Alembic이 소유하는 나머지 테이블 (확정 D-13, §1-6):
- job (오프라인 배치 적재)
- job_profile, skill_stat, unmapped_skill, user_competency,
  job_profile_build_lock, collection_cursor (Worker 런타임)
그리고 ncs_unit.is_verified 컬럼 추가 (확정 D-17).

Core 소유 테이블(users, roadmap, quest, ...)은 여기서 다루지 않는다 (C-1).

Revision ID: 0002_worker_owned_tables
Revises: 0001_ncs_offline_tables
Create Date: 2026-07-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0002_worker_owned_tables"
down_revision: Union[str, None] = "0001_ncs_offline_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── ncs_unit.is_verified (확정 D-17) ──────────────────────────────────
    op.add_column(
        "ncs_unit",
        sa.Column(
            "is_verified", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )

    # ── job (직무 마스터, PART E) ─────────────────────────────────────────
    op.create_table(
        "job",
        sa.Column("job_code", sa.String(), primary_key=True),
        sa.Column("job_name", sa.String(), nullable=False),
        sa.Column("category_code", sa.String(), nullable=True),
        sa.Column("category_name", sa.String(), nullable=True),
        sa.Column("tagline", sa.Text(), nullable=True),
    )

    # ── job_profile (직무별 재료, PART E) ─────────────────────────────────
    op.create_table(
        "job_profile",
        sa.Column("job_code", sa.String(), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("axes", JSONB(), nullable=False),
        sa.Column("skills", JSONB(), nullable=False),
        sa.Column("levels", JSONB(), nullable=False),
        sa.Column("prerequisites", JSONB(), nullable=False),
        sa.Column("questions", JSONB(), nullable=False),
        sa.Column("quest_templates", JSONB(), nullable=False),
        sa.Column("activity_quests", JSONB(), nullable=False),
        sa.Column(
            "built_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ── skill_stat (P·S 근거, F-3) ────────────────────────────────────────
    op.create_table(
        "skill_stat",
        sa.Column("job_code", sa.String(), primary_key=True),
        sa.Column("skill_code", sa.String(), primary_key=True),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "entry_level_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ── unmapped_skill (미매핑 스킬, F-4 + 확정 §1-3) ─────────────────────
    op.create_table(
        "unmapped_skill",
        sa.Column("skill_code", sa.String(), primary_key=True),
        sa.Column("job_code", sa.String(), primary_key=True),
        sa.Column("occurrence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "status", sa.String(), nullable=False, server_default="PENDING"
        ),  # PENDING | MAPPED | IGNORED
        sa.Column("suggested_ncs_unit_code", sa.String(), nullable=True),
    )

    # ── user_competency (AI 보정, G-6) ────────────────────────────────────
    op.create_table(
        "user_competency",
        sa.Column("roadmap_id", sa.BigInteger(), primary_key=True),
        sa.Column("skill_code", sa.String(), primary_key=True),
        sa.Column("mastery", sa.Numeric(3, 2), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Numeric(3, 2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ── job_profile_build_lock (중복 빌드 방지, F-0) ──────────────────────
    op.create_table(
        "job_profile_build_lock",
        sa.Column("job_code", sa.String(), primary_key=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("status", sa.String(), nullable=False),  # IN_PROGRESS | DONE | FAILED
    )

    # ── collection_cursor (증분 수집 커서, F-1 / I-3) ─────────────────────
    op.create_table(
        "collection_cursor",
        sa.Column("job_code", sa.String(), primary_key=True),
        sa.Column("last_cursor", sa.String(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("collection_cursor")
    op.drop_table("job_profile_build_lock")
    op.drop_table("user_competency")
    op.drop_table("unmapped_skill")
    op.drop_table("skill_stat")
    op.drop_table("job_profile")
    op.drop_table("job")
    op.drop_column("ncs_unit", "is_verified")
