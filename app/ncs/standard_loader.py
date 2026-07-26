"""ncs_unit 적재 (I-2). 일회성 배치 (PART K):

    docker compose run --rm worker python -m app.ncs.standard_loader

소스는 get_ncs_source()가 고른다 — 키 없으면 시드, 있으면 API. 멱등(upsert)이라
여러 번 돌려도 안전하다.
"""

import logging
from dataclasses import asdict

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.ncs.source import NcsSource, get_ncs_source
from app.persistence.database import session_scope
from app.persistence.models import NcsUnit

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("myith.ncs.standard")


def load_units(session: Session, source: NcsSource) -> int:
    records = source.fetch_units()
    for r in records:
        values = asdict(r)
        stmt = insert(NcsUnit).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["code"],
            set_={k: v for k, v in values.items() if k != "code"},
        )
        session.execute(stmt)
    return len(records)


def main() -> None:
    source = get_ncs_source()
    logger.info("ncs_unit 적재 시작: source=%s", type(source).__name__)
    with session_scope() as session:
        n = load_units(session, source)
    logger.info("ncs_unit 적재 완료: %d건", n)


if __name__ == "__main__":
    main()
