"""job·job_profile 시드 로더. 멱등 upsert (확정 Step 1).

NCS 3종은 app/ncs 로더가 담당한다 — 여기서는 다루지 않는다.
"""

import json
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.persistence.models import Job, JobProfile
from app.seed import SEED_DATA_DIR

# job_profile의 JSONB 컬럼 (built_at은 server_default now()로 자동)
_PROFILE_JSON_COLUMNS = (
    "axes",
    "skills",
    "levels",
    "prerequisites",
    "questions",
    "quest_templates",
    "activity_quests",
)


def _load_json(filename: str, seed_dir: Path = SEED_DATA_DIR) -> list[dict]:
    with (seed_dir / filename).open(encoding="utf-8") as f:
        return json.load(f)


def load_jobs(session: Session, seed_dir: Path = SEED_DATA_DIR) -> int:
    rows = _load_json("job.json", seed_dir)
    for r in rows:
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
        values = {"job_code": r["job_code"], "version": r["version"]}
        values.update({col: r[col] for col in _PROFILE_JSON_COLUMNS})
        stmt = insert(JobProfile).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["job_code", "version"],
            set_={col: r[col] for col in _PROFILE_JSON_COLUMNS},
        )
        session.execute(stmt)
    return len(rows)
