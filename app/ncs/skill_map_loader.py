"""skill_ncs_map 적재. 일회성 배치 (PART K):

    docker compose run --rm worker python -m app.ncs.skill_map_loader

skill_ncs_map은 API가 없다 — NCS 정의 + 사람 검수의 큐레이션 산출물이라(PART K)
시드/파일에서만 읽는다.

F-4 규칙을 적재 전에 강제한다: is_primary는 스킬당 정확히 하나. 위반 시 적재하지
않고 실패시킨다 — 근거 없는 축 배정을 막기 위함.
"""

import argparse
import json
import logging
from collections import Counter
from pathlib import Path

from sqlalchemy import delete, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.ncs.records import SkillNcsMapRecord
from app.ncs.source import SEED_DIR
from app.persistence.database import session_scope
from app.persistence.models import SkillNcsMap

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("myith.ncs.skill_map")


def load_seed(seed_dir: Path = SEED_DIR) -> list[SkillNcsMapRecord]:
    path = seed_dir / "skill_ncs_map.json"
    with path.open(encoding="utf-8") as f:
        return [SkillNcsMapRecord(**row) for row in json.load(f)]


def validate_primary_uniqueness(records: list[SkillNcsMapRecord]) -> None:
    """F-4: 스킬당 primary 매핑은 정확히 하나. 아니면 ValueError."""
    primary_count: Counter[str] = Counter()
    for r in records:
        if r.is_primary:
            primary_count[r.skill_code] += 1

    all_skills = {r.skill_code for r in records}
    offenders = {
        skill: primary_count.get(skill, 0)
        for skill in all_skills
        if primary_count.get(skill, 0) != 1
    }
    if offenders:
        raise ValueError(
            f"is_primary는 스킬당 정확히 하나여야 한다 (F-4). 위반: {offenders}"
        )


def load_skill_map(
    session: Session, records: list[SkillNcsMapRecord], prune: bool = False
) -> int:
    validate_primary_uniqueness(records)
    for r in records:
        stmt = insert(SkillNcsMap).values(
            skill_code=r.skill_code,
            ncs_unit_code=r.ncs_unit_code,
            is_primary=r.is_primary,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["skill_code", "ncs_unit_code"],
            set_={"is_primary": r.is_primary},
        )
        session.execute(stmt)
    if prune:
        _prune_skill_map(session, records)
    return len(records)


def _prune_skill_map(session: Session, records: list[SkillNcsMapRecord]) -> int:
    """시드에 없는 (skill_code, ncs_unit_code) 행을 같은 트랜잭션에서 삭제한다.

    upsert만으로는 옛 시드에서 사라진 매핑이 DB에 남는다. 같은 skill_code가 다른
    ncs_unit_code로 두 행 남으면 둘 다 is_primary=true가 되어 F-4(스킬당 primary 하나)가
    깨지고 6축 고정이 무너진다. --prune일 때만 호출한다(운영 중 실수 방지).
    """
    seed_keys = [(r.skill_code, r.ncs_unit_code) for r in records]
    if not seed_keys:  # 빈 시드로 전체 삭제하는 사고 방지 (유령보다 데이터 유실이 나쁘다)
        return 0
    stmt = delete(SkillNcsMap).where(
        tuple_(SkillNcsMap.skill_code, SkillNcsMap.ncs_unit_code).notin_(seed_keys)
    )
    deleted = session.execute(stmt).rowcount
    if deleted:
        logger.info("skill_ncs_map prune: 시드에 없는 %d행 삭제", deleted)
    return deleted


def main(prune: bool = False) -> None:
    records = load_seed()
    logger.info("skill_ncs_map 적재 시작: %d행 (prune=%s)", len(records), prune)
    with session_scope() as session:
        n = load_skill_map(session, records, prune=prune)
    logger.info("skill_ncs_map 적재 완료: %d행", n)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="skill_ncs_map 시드 적재")
    parser.add_argument(
        "--prune",
        action="store_true",
        help="시드에 없는 (skill_code, ncs_unit_code) 행을 삭제한다 (기본: upsert만)",
    )
    args = parser.parse_args()
    main(prune=args.prune)
