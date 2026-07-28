"""SQLAlchemy 선언적 Base + 모델.

이 저장소 Alembic이 소유하는 테이블만 여기 정의한다 (C-1, PART E, 확정 D-13).
Core 소유 테이블(users, roadmap, quest, ...)의 DDL은 절대 여기 넣지 않는다 —
필요하면 raw SQL/읽기 전용으로 조회만 한다.

소유 테이블 (확정 D-13, §1-6):
- 오프라인 배치 적재 : job, ncs_unit, ncs_certification, skill_ncs_map
- Worker 런타임 쓰기 : job_profile, user_competency, skill_stat, unmapped_skill,
                       job_profile_build_lock, collection_cursor
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import DateTime


class Base(DeclarativeBase):
    pass


# ── 오프라인 배치 소유 (적재는 app/ncs 배치, 런타임엔 읽기 전용) ────────────


class Job(Base):
    """직무 마스터 (PART E). 오프라인 배치가 적재, Core가 직무 선택 화면에서 읽는다."""

    __tablename__ = "job"

    job_code: Mapped[str] = mapped_column(String, primary_key=True)
    job_name: Mapped[str] = mapped_column(String, nullable=False)
    category_code: Mapped[str | None] = mapped_column(String, nullable=True)
    category_name: Mapped[str | None] = mapped_column(String, nullable=True)
    tagline: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 직무 ↔ NCS 세분류 연결 (확정 W2 C-6). backend·frontend='20010202'. 확장 대비 nullable.
    ncs_detail_code: Mapped[str | None] = mapped_column(String, nullable=True)


class NcsUnit(Base):
    """NCS 능력단위. level(1~8)이 난이도 공식의 N값 근거 (F-5, I-2).

    is_verified: 실제 NCS 코드로 검증된 행만 true (확정 D-17). 시드의 임시 코드
    (TBD-NCS-xx)는 false로 두고, 화면에서 코드를 노출하지 않는다.
    """

    __tablename__ = "ncs_unit"

    code: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False)  # 1~8
    is_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    major_name: Mapped[str | None] = mapped_column(String, nullable=True)
    middle_name: Mapped[str | None] = mapped_column(String, nullable=True)
    minor_name: Mapped[str | None] = mapped_column(String, nullable=True)
    detail_name: Mapped[str | None] = mapped_column(String, nullable=True)


class NcsCertification(Base):
    """능력단위–자격 종목 연계 (I-3). 한 능력단위에 연계된 자격은 전부 저장."""

    __tablename__ = "ncs_certification"

    ncs_unit_code: Mapped[str] = mapped_column(
        String, ForeignKey("ncs_unit.code"), primary_key=True
    )
    cert_code: Mapped[str] = mapped_column(String, primary_key=True)
    cert_name: Mapped[str] = mapped_column(String, nullable=False)
    unit_type: Mapped[str | None] = mapped_column(String, nullable=True)  # 필수/선택


class SkillNcsMap(Base):
    """스킬 → NCS 능력단위 매핑. is_primary는 스킬당 정확히 하나 (F-4).

    (스킬당 하나만 true) 규칙은 DB 제약으로 강제하기 애매해 적재 단계에서
    검증한다 (app/ncs/skill_map_loader.validate_primary_uniqueness).
    """

    __tablename__ = "skill_ncs_map"

    skill_code: Mapped[str] = mapped_column(String, primary_key=True)
    ncs_unit_code: Mapped[str] = mapped_column(
        String, ForeignKey("ncs_unit.code"), primary_key=True
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


# ── Worker 런타임 소유 (쓰기) ─────────────────────────────────────────────


class JobProfile(Base):
    """직무별 재료 (PART E). 파이프라인 1이 새 버전으로 저장, Core가 조립 시 읽는다.

    quest_templates 각 항목: {skillCode, title, completionCriteria, ncsUnitCode,
    guidance:{none, aware, experienced, proficient}} (확정 W2 B-1, D-03-a).
    """

    __tablename__ = "job_profile"

    job_code: Mapped[str] = mapped_column(String, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    axes: Mapped[list] = mapped_column(JSONB, nullable=False)
    skills: Mapped[list] = mapped_column(JSONB, nullable=False)
    levels: Mapped[list] = mapped_column(JSONB, nullable=False)
    prerequisites: Mapped[list] = mapped_column(JSONB, nullable=False)
    questions: Mapped[list] = mapped_column(JSONB, nullable=False)
    quest_templates: Mapped[list] = mapped_column(JSONB, nullable=False)
    activity_quests: Mapped[list] = mapped_column(JSONB, nullable=False)
    built_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SkillStat(Base):
    """P·S 산출 근거. 증분 수집마다 누적 (F-3). 원본 공고는 저장하지 않는다."""

    __tablename__ = "skill_stat"

    job_code: Mapped[str] = mapped_column(String, primary_key=True)
    skill_code: Mapped[str] = mapped_column(String, primary_key=True)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    entry_level_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UnmappedSkill(Base):
    """NCS 매핑 없는 신규 스킬 (F-4). 로드맵에서 제외하지 않고 큐레이션 대기열로 기록.

    suggested_ncs_unit_code: 동시 출현 힌트(확정 §1-3). 자동 확정하지 않는다 —
    사람 검수 시간을 줄이는 용도.
    """

    __tablename__ = "unmapped_skill"

    skill_code: Mapped[str] = mapped_column(String, primary_key=True)
    job_code: Mapped[str] = mapped_column(String, primary_key=True)
    occurrence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    status: Mapped[str] = mapped_column(
        String, nullable=False, server_default="PENDING"
    )  # PENDING | MAPPED | IGNORED
    suggested_ncs_unit_code: Mapped[str | None] = mapped_column(String, nullable=True)


class UserCompetency(Base):
    """AI 보정 결과 + evidence (G-6). Core가 자가진단과 병합한다.

    roadmap_id는 숫자(Long) — 메시지 payload 기준. API의 접두사 문자열이 아님 (D-9).
    """

    __tablename__ = "user_competency"

    roadmap_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    skill_code: Mapped[str] = mapped_column(String, primary_key=True)
    mastery: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)  # 원문 인용, 상한 적용
    confidence: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UserQuestGuidance(Base):
    """층2 개인화 문구 (확정 W-H1-C, H-1). Worker 쓰기 / Core 조립 시 읽어 층1 위에 덮는다.

    비어 있으면 Core가 층1 템플릿(quest_templates[].guidance 4종)을 쓴다 — 폴백이 공짜다.
    user_competency와 정확히 같은 패턴(조립 시점 DB 읽기). tier는 층1이 고른 값을 함께 저장해
    폴백 시 Core가 어느 문구를 골랐는지 재현·검증할 수 있게 한다.
    """

    __tablename__ = "user_quest_guidance"

    roadmap_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    skill_code: Mapped[str] = mapped_column(String, primary_key=True)
    guidance: Mapped[str] = mapped_column(Text, nullable=False)  # 층2가 다듬은 최종 문구 1개
    tier: Mapped[str] = mapped_column(String, nullable=False)  # none|aware|experienced|proficient
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class JobProfileBuildLock(Base):
    """중복 빌드 방지 (F-0)."""

    __tablename__ = "job_profile_build_lock"

    job_code: Mapped[str] = mapped_column(String, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    status: Mapped[str] = mapped_column(
        String, nullable=False
    )  # IN_PROGRESS | DONE | FAILED


class CollectionCursor(Base):
    """증분 수집 커서 (F-1). 채용 소스 증분 수집용."""

    __tablename__ = "collection_cursor"

    job_code: Mapped[str] = mapped_column(String, primary_key=True)
    last_cursor: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WorkerProcessedEvent(Base):
    """Worker 수신 멱등 (확정 W2 A-1, D-6). Core 소유 `processed_event`와 별개 테이블 —
    같은 DB를 공유하므로 이름이 겹치면 서로의 eventId 공간이 충돌한다.

    멱등 체크는 DB 고유 제약으로만 한다. SELECT 후 INSERT는 동시 수신 시 뚫린다.
    """

    __tablename__ = "worker_processed_event"

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    consumed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class NcsLoadCursor(Base):
    """NCS 오프라인 배치 재개 커서 (확정 W2 D-3). 자격종목 API는 1,000건/일 —
    쿼터 초과 시 커서를 남기고 정상 종료, 재실행 시 이어서 적재한다.
    """

    __tablename__ = "ncs_load_cursor"

    loader_name: Mapped[str] = mapped_column(String, primary_key=True)  # 'certification'
    last_unit_code: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
