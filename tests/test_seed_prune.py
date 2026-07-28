"""시드 --prune 라운드트립: 옛 시드 → 새 시드(prune) → DB가 새 시드와 정확히 일치.

유령 데이터 문제(loaders/skill_map_loader가 upsert만 하고 DELETE를 안 해 옛 시드의
사라진 행이 DB에 남음)를 재현하고, --prune이 그것을 정리하는지 검증한다.

DB가 필요한 테스트(DELETE 라운드트립은 순수함수로 못 본다)라 SQLite 인메모리를 쓴다.
로더는 postgres `insert().on_conflict_do_update`를 쓰므로 SQLite 컴파일이 안 된다 —
같은 시그니처의 sqlite `insert`로 갈아끼워(monkeypatch) upsert+prune 경로를 그대로 태운다.
prune 로직 자체(delete + tuple_ notin_)는 방언 무관이라 이 대체로 충실히 검증된다.
"""

import json

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.ncs.records import SkillNcsMapRecord
from app.ncs.skill_map_loader import load_skill_map
from app.persistence.models import Job, SkillNcsMap
from app.seed.loaders import load_jobs


@pytest.fixture
def session(monkeypatch):
    """job·skill_ncs_map만 있는 SQLite 인메모리 세션. postgres insert를 sqlite로 대체."""
    from sqlalchemy.orm import sessionmaker

    engine = create_engine("sqlite://")
    # 이 두 테이블만 만든다 — job_profile(JSONB)·worker_processed_event(UUID)는 SQLite에서
    # 생성이 안 되고, prune 대상도 아니라 불필요하다. skill_ncs_map의 ncs_unit FK는
    # SQLite에서 미강제(pragma off)라 ncs_unit 테이블 없이도 생성·삽입된다.
    Job.__table__.create(engine)
    SkillNcsMap.__table__.create(engine)
    # 로더의 on_conflict_do_update를 SQLite 방언으로 태운다(index_elements/set_ 시그니처 동일).
    monkeypatch.setattr("app.seed.loaders.insert", sqlite_insert)
    monkeypatch.setattr("app.ncs.skill_map_loader.insert", sqlite_insert)
    sess = sessionmaker(bind=engine, future=True)()
    try:
        yield sess
        sess.commit()
    finally:
        sess.close()
        engine.dispose()


# ── skill_ncs_map ────────────────────────────────────────────────────────

# 옛 시드: java의 축이 u_old였고 react가 존재했다.
_OLD_MAP = [
    SkillNcsMapRecord("java", "u_old", True),
    SkillNcsMapRecord("git", "u_git", True),
    SkillNcsMapRecord("react", "u_react", True),
]
# 새 시드: java의 축이 u_new로 바뀌고 react는 빠졌다.
_NEW_MAP = [
    SkillNcsMapRecord("java", "u_new", True),
    SkillNcsMapRecord("git", "u_git", True),
]


def _map_rows(session):
    return session.execute(
        select(SkillNcsMap.skill_code, SkillNcsMap.ncs_unit_code, SkillNcsMap.is_primary)
    ).all()


def _primary_per_skill(session):
    rows = session.execute(
        select(SkillNcsMap.skill_code, func.count())
        .where(SkillNcsMap.is_primary.is_(True))
        .group_by(SkillNcsMap.skill_code)
    ).all()
    return {skill: n for skill, n in rows}


def test_skill_map_without_prune_leaves_ghost_and_breaks_f4(session):
    """prune 없이 새 시드를 얹으면 java가 u_old·u_new 두 primary 행으로 남는다(버그 재현)."""
    load_skill_map(session, _OLD_MAP, prune=False)
    load_skill_map(session, _NEW_MAP, prune=False)  # upsert만

    # java→u_old, java→u_new, git→u_git, react→u_react = 4행. java·react가 유령으로 남는다.
    assert len(_map_rows(session)) == 4
    assert _primary_per_skill(session)["java"] == 2  # F-4 위반


def test_skill_map_prune_matches_new_seed_and_keeps_f4(session):
    """옛 시드 → 새 시드(prune) → DB가 새 시드와 정확히 일치, is_primary는 스킬당 1개."""
    load_skill_map(session, _OLD_MAP, prune=False)
    load_skill_map(session, _NEW_MAP, prune=True)

    rows = {(s, u) for s, u, _ in _map_rows(session)}
    assert rows == {("java", "u_new"), ("git", "u_git")}  # react·java→u_old 삭제됨
    assert len(rows) == len(_NEW_MAP)  # 행 수 == 새 시드
    # F-4: is_primary가 skill_code당 정확히 1개
    for skill, n in _primary_per_skill(session).items():
        assert n == 1, f"{skill} primary {n}개 (F-4 위반)"


def test_skill_map_prune_empty_seed_is_noop(session):
    """빈 시드로 prune하면 전체를 지우지 않는다 — 유령보다 운영 데이터 유실이 나쁘다."""
    load_skill_map(session, _OLD_MAP, prune=False)
    load_skill_map(session, [], prune=True)  # 빈 시드: 가드가 삭제를 막아야
    assert len(_map_rows(session)) == 3


# ── job ──────────────────────────────────────────────────────────────────

_OLD_JOBS = [
    {"job_code": "backend", "job_name": "백엔드"},
    {"job_code": "frontend", "job_name": "프론트엔드"},
    {"job_code": "data-engineer", "job_name": "데이터 엔지니어"},
    {"job_code": "devops", "job_name": "데브옵스"},
    {"job_code": "qa", "job_name": "QA"},
]
_NEW_JOBS = [
    {"job_code": "backend", "job_name": "백엔드"},
    {"job_code": "frontend", "job_name": "프론트엔드"},
]


def _write_jobs(seed_dir, rows):
    (seed_dir / "job.json").write_text(json.dumps(rows), encoding="utf-8")


def _job_codes(session):
    return {c for (c,) in session.execute(select(Job.job_code)).all()}


def test_jobs_without_prune_keeps_ghosts(session, tmp_path):
    """prune 없이는 data-engineer·devops·qa 유령 직무가 그대로 남는다(버그 재현)."""
    _write_jobs(tmp_path, _OLD_JOBS)
    load_jobs(session, seed_dir=tmp_path, prune=False)
    _write_jobs(tmp_path, _NEW_JOBS)
    load_jobs(session, seed_dir=tmp_path, prune=False)
    assert _job_codes(session) == {"backend", "frontend", "data-engineer", "devops", "qa"}


def test_jobs_prune_removes_ghosts(session, tmp_path):
    """옛 시드 → 새 시드(prune) → job 행이 정확히 새 시드와 일치."""
    _write_jobs(tmp_path, _OLD_JOBS)
    load_jobs(session, seed_dir=tmp_path, prune=False)
    _write_jobs(tmp_path, _NEW_JOBS)
    load_jobs(session, seed_dir=tmp_path, prune=True)
    assert _job_codes(session) == {"backend", "frontend"}


def test_jobs_prune_empty_seed_is_noop(session, tmp_path):
    _write_jobs(tmp_path, _OLD_JOBS)
    load_jobs(session, seed_dir=tmp_path, prune=False)
    _write_jobs(tmp_path, [])
    load_jobs(session, seed_dir=tmp_path, prune=True)
    assert len(_job_codes(session)) == 5


# ── job_profile은 prune 대상이 아니다 (판단: 런타임 소유·D-8/F-10) ──────────


def test_job_profiles_loader_has_no_prune_param():
    """load_job_profiles에 prune을 추가하면 안 된다 — 런타임이 만든 버전과 기존 로드맵이
    참조하는 profile_version이 날아간다. 이 결정을 코드로 못 박아 회귀를 막는다."""
    import inspect

    from app.seed.loaders import load_job_profiles

    assert "prune" not in inspect.signature(load_job_profiles).parameters
