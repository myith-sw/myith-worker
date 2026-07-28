"""시드 전체 적재 오케스트레이터 (확정 Step 1):

    python -m app.seed.load_all

한 트랜잭션에서 NCS 3종 + job + job_profile을 멱등 upsert한다. FK 때문에
ncs_unit을 먼저 적재한다 (certification·skill_ncs_map이 참조).

load_all은 항상 시드 소스를 쓴다. API 소스는 오프라인 배치(standard_loader를
직접 실행)의 몫이다 — NCS_SERVICE_KEY가 있어도 여기서는 시드를 적재한다.
"""

import argparse
import logging

from app.ncs.certification_loader import load_certifications
from app.ncs.skill_map_loader import load_seed as load_skill_seed
from app.ncs.skill_map_loader import load_skill_map
from app.ncs.source import SeedNcsSource
from app.ncs.standard_loader import load_units
from app.persistence.database import session_scope
from app.seed.loaders import load_job_profiles, load_jobs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("myith.seed")


def main(prune: bool = False) -> None:
    source = SeedNcsSource()  # load_all은 항상 시드. API는 오프라인 배치 전용.
    logger.info("시드 적재 시작 (source=SeedNcsSource, prune=%s)", prune)
    with session_scope() as session:
        units = load_units(session, source)  # FK 때문에 가장 먼저
        certs = load_certifications(session, source)
        # prune은 job·skill_ncs_map만. ncs_unit·ncs_certification은 공공데이터 누적이라
        # 삭제 안 함. job_profile은 런타임 소유라 삭제 안 함(loaders.load_job_profiles 주석).
        maps = load_skill_map(session, load_skill_seed(), prune=prune)
        jobs = load_jobs(session, prune=prune)
        profiles = load_job_profiles(session)
    logger.info(
        "시드 적재 완료: ncs_unit=%d, ncs_certification=%d, skill_ncs_map=%d, "
        "job=%d, job_profile=%d",
        units,
        certs,
        maps,
        jobs,
        profiles,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="시드 전체 적재")
    parser.add_argument(
        "--prune",
        action="store_true",
        help="시드에 없는 job·skill_ncs_map 행을 삭제한다 "
        "(ncs_unit·ncs_certification·job_profile은 대상 아님. 기본: upsert만)",
    )
    args = parser.parse_args()
    main(prune=args.prune)
