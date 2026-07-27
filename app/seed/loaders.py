"""job·job_profile 시드 로더. 멱등 upsert (확정 Step 1).

NCS 3종은 app/ncs 로더가 담당한다 — 여기서는 다루지 않는다.
"""

import json
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.persistence.models import Job, JobProfile
from app.seed import SEED_DATA_DIR

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


def load_jobs(session: Session, seed_dir: Path = SEED_DATA_DIR) -> int:
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
    return len(rows)


def load_job_profiles(session: Session, seed_dir: Path = SEED_DATA_DIR) -> int:
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
