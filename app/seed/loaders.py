"""job·job_profile 시드 로더. 멱등 upsert (확정 Step 1).

NCS 3종은 app/ncs 로더가 담당한다 — 여기서는 다루지 않는다.
"""

import json
import logging
from pathlib import Path

from sqlalchemy import delete, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.persistence.models import Job, JobProfile
from app.seed import SEED_DATA_DIR
from app.seed.overrides import load_tagline_overrides

logger = logging.getLogger("myith.seed.loaders")

# job_profile.json은 최상위 키가 camelCase다(생성기 gen_seed 출력 + Core JSONB 계약).
# DB 컬럼은 snake_case이므로 최상위만 매핑한다. 중첩 JSONB 내용(axisCode·ncsUnitCode·
# skillCode 등 camelCase)은 파싱하지 않고 그대로 저장한다 — Core가 그 형태로 읽는다(PART E).
# 최상위 ncsDetailCode는 여기서 무시한다 — job.ncs_detail_code가 정본이다.
_PROFILE_COLUMN_TO_KEY = {
    "axes": "axes",
    "skills": "skills",
    "levels": "levels",
    "prerequisites": "prerequisites",
    "questions": "questions",
    "quest_templates": "questTemplates",
    "activity_quests": "activityQuests",
}


def _load_json(filename: str, seed_dir: Path = SEED_DATA_DIR) -> list[dict]:
    with (seed_dir / filename).open(encoding="utf-8") as f:
        return json.load(f)


def load_jobs(
    session: Session, seed_dir: Path = SEED_DATA_DIR, prune: bool = False
) -> int:
    rows = _load_json("job.json", seed_dir)
    for r in rows:
        # available은 Core가 job_profile 존재 여부로 파생한다(JobQueryService.profile.isPresent()).
        # job 테이블에 컬럼이 없다 — job.json의 available은 의도 표기일 뿐 DB에 저장하지 않는다.
        values = {
            "job_code": r["job_code"],
            "job_name": r["job_name"],
            "category_code": r.get("category_code"),
            "category_name": r.get("category_name"),
            "tagline": r.get("tagline"),
            "ncs_detail_code": r.get("ncs_detail_code"),  # W2 C-6
        }
        stmt = insert(Job).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["job_code"],
            set_={k: v for k, v in values.items() if k != "job_code"},
        )
        session.execute(stmt)
    # 검수 tagline 오버라이드 반영 (화면 텍스트 검수, review_apply가 채움). 없으면 무영향.
    _apply_tagline_overrides(session)
    if prune:
        _prune_jobs(session, rows)
    return len(rows)


def _apply_tagline_overrides(session: Session) -> int:
    """review_apply가 채운 tagline을 job에 덮어쓴다. 원본 job.json은 수정하지 않는다.

    파일을 비우면 다음 적재부터 원문(job.json) tagline으로 원복된다(docs/review-apply.md).
    """
    overrides = load_tagline_overrides()
    for job_code, tagline in overrides.items():
        session.execute(
            update(Job).where(Job.job_code == job_code).values(tagline=tagline)
        )
    if overrides:
        logger.info("tagline 오버라이드 %d건 반영", len(overrides))
    return len(overrides)


def _prune_jobs(session: Session, rows: list[dict]) -> int:
    """시드에 없는 job_code 행을 같은 트랜잭션에서 삭제한다.

    upsert만으로는 옛 시드에서 사라진 직무가 DB에 남아 /api/jobs에 job_profile 없는
    available:false 유령 직무로 뜨고, Core가 그에 대해 JobProfileBuildRequested를 계속
    발행한다. --prune일 때만 호출한다(운영 중 실수 방지). job_profile은 삭제하지 않는다
    — load_job_profiles 주석 참조.
    """
    seed_codes = [r["job_code"] for r in rows]
    if not seed_codes:  # 빈 시드로 전체 삭제하는 사고 방지
        return 0
    deleted = session.execute(
        delete(Job).where(Job.job_code.notin_(seed_codes))
    ).rowcount
    if deleted:
        logger.info("job prune: 시드에 없는 %d행 삭제", deleted)
    return deleted


def load_job_profiles(session: Session, seed_dir: Path = SEED_DATA_DIR) -> int:
    # prune 없음(의도적). job_profile은 시드 전용이 아니라 파이프라인 1이 새 버전으로 계속
    # 쓰는 런타임 소유 데이터다. 시드 키셋(현재 10직무 version=1)에 맞춰 삭제하면 런타임이
    # 만든 버전과 기존 로드맵이 참조하는 profile_version이 날아간다(D-8/F-10). 유령 문제는
    # job·skill_ncs_map에만 있으므로 여기선 upsert만 한다.
    rows = _load_json("job_profile.json", seed_dir)
    for r in rows:
        values = {"job_code": r["jobCode"], "version": r["version"]}
        values.update({col: r[key] for col, key in _PROFILE_COLUMN_TO_KEY.items()})
        stmt = insert(JobProfile).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["job_code", "version"],
            set_={col: r[key] for col, key in _PROFILE_COLUMN_TO_KEY.items()},
        )
        session.execute(stmt)
    return len(rows)
