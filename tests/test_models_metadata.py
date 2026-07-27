"""모델 메타데이터가 소유 테이블만 담는지 검증 (C-1, 확정 D-13).

Core 소유 테이블(users, roadmap, quest, ...)이 섞여 들어가면 Alembic이 그것들의
DDL을 만들려 하고 Core와 충돌한다. 여기서 자물쇠를 건다.
"""

from app.persistence.models import Base

# 확정 D-13 / §1-6 / W2 A-1·D-3: 이 저장소 Alembic이 소유하는 테이블 전부.
OWNED_TABLES = {
    "job",
    "job_profile",
    "ncs_unit",
    "ncs_certification",
    "skill_ncs_map",
    "user_competency",
    "skill_stat",
    "unmapped_skill",
    "job_profile_build_lock",
    "collection_cursor",
    "worker_processed_event",  # W2 A-1: Core `processed_event`와 별개
    "ncs_load_cursor",  # W2 D-3: 자격 적재 재개 커서
}

# Core Flyway 소유. 여기 메타데이터에 절대 나타나면 안 된다.
CORE_TABLES = {
    "users",
    "roadmap",
    "character",
    "quest",
    "user_diagnosis",
    "star_record",
    "dashboard_snapshot",
    "outbox",
    "processed_event",
    "flyway_schema_history",
}


def test_metadata_contains_exactly_owned_tables():
    assert set(Base.metadata.tables) == OWNED_TABLES


def test_no_core_tables_leaked_into_metadata():
    assert set(Base.metadata.tables).isdisjoint(CORE_TABLES)


def test_ncs_unit_has_is_verified_column():
    assert "is_verified" in Base.metadata.tables["ncs_unit"].columns


def test_unmapped_skill_has_suggested_column():
    cols = Base.metadata.tables["unmapped_skill"].columns
    assert "suggested_ncs_unit_code" in cols


def test_job_has_ncs_detail_code_column():
    assert "ncs_detail_code" in Base.metadata.tables["job"].columns


def test_worker_processed_event_pk_is_event_id():
    pk = [c.name for c in Base.metadata.tables["worker_processed_event"].primary_key]
    assert pk == ["event_id"]
