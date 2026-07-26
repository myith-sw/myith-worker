"""ncs_certification 적재 (I-3). 일회성 배치 (PART K):

    docker compose run --rm worker python -m app.ncs.certification_loader

한 능력단위에 연계된 자격은 전부 저장한다. 없으면 아무것도 저장하지 않는다.
ncs_unit이 먼저 적재돼 있어야 한다(FK). standard_loader를 먼저 돌린다.
"""

import logging
from dataclasses import asdict

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.ncs.source import NcsSource, get_ncs_source
from app.persistence.database import session_scope
from app.persistence.models import NcsCertification

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("myith.ncs.certification")


def load_certifications(session: Session, source: NcsSource) -> int:
    records = source.fetch_certifications()
    for r in records:
        values = asdict(r)
        stmt = insert(NcsCertification).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["ncs_unit_code", "cert_code"],
            set_={"cert_name": values["cert_name"], "unit_type": values["unit_type"]},
        )
        session.execute(stmt)
    return len(records)


def main() -> None:
    source = get_ncs_source()
    logger.info("ncs_certification 적재 시작: source=%s", type(source).__name__)
    with session_scope() as session:
        n = load_certifications(session, source)
    logger.info("ncs_certification 적재 완료: %d건", n)


if __name__ == "__main__":
    main()
