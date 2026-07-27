"""ncs_certification 적재 (I-3). 일회성 배치 (PART K):

    docker compose run --rm worker python -m app.ncs.certification_loader

한 능력단위에 연계된 자격은 전부 저장한다. 없으면 아무것도 저장하지 않는다.
ncs_unit이 먼저 적재돼 있어야 한다(FK). standard_loader를 먼저 돌린다.
"""

import logging
from dataclasses import asdict

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.ncs.records import NcsCertRecord
from app.ncs.source import NcsSource, get_ncs_source
from app.persistence.database import session_scope
from app.persistence.models import NcsCertification

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("myith.ncs.certification")

MANDATORY_UNIT_TYPE = "필수"


def dedupe_certifications(records: list[NcsCertRecord]) -> list[NcsCertRecord]:
    """(ncs_unit_code, cert_code) 중복을 결정론적으로 접는다.

    같은 (능력단위, 자격종목)이 표준버전만 다르게 여러 행 오면 PK가 충돌한다. 이때
    on_conflict가 파일 순서상 마지막 값을 남기면 정렬만 바뀌어도 결과가 달라져 멱등이
    깨진다(같은 데이터 재적재 시 unit_type이 필수↔선택으로 흔들림). 그래서 적재 전에 접는다:
      - unit_type '필수'가 '선택'을 이긴다 (화면 '추천 자격'에서 더 강한 신호).
      - 둘 다 같은 유형이면 먼저 나온 행 (내용 동일).
      - 출력은 (능력단위, 자격)으로 정렬 → 입력 순서와 무관하게 항상 같은 리스트.
    접은 건수는 로그로 남긴다 (조용히 버리지 않는다).
    """
    best: dict[tuple[str, str], NcsCertRecord] = {}
    for r in records:
        key = (r.ncs_unit_code, r.cert_code)
        cur = best.get(key)
        if cur is None:
            best[key] = r
        elif cur.unit_type != MANDATORY_UNIT_TYPE and r.unit_type == MANDATORY_UNIT_TYPE:
            best[key] = r  # 필수가 선택을 대체
    collapsed = len(records) - len(best)
    if collapsed:
        logger.info(
            "자격연계 중복 %d행 접음 (필수 우선): %d → %d행",
            collapsed,
            len(records),
            len(best),
        )
    return [best[k] for k in sorted(best)]


def load_certifications(session: Session, source: NcsSource) -> int:
    records = dedupe_certifications(source.fetch_certifications())
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
