"""NCS 데이터 소스 추상화.

지금은 시드(JSON)로 채운다. NCS_SERVICE_KEY가 확보되면 ApiNcsSource를 구현해
같은 인터페이스로 교체한다 — 로더는 소스가 무엇인지 몰라도 된다 (I-2/I-3).

skill_ncs_map은 API가 없다 — NCS 정의 + 사람 검수의 큐레이션 산출물이라(PART K)
항상 시드/파일에서 읽는다. 여기 소스는 units·certifications만 추상화한다.
"""

import json
import logging
from pathlib import Path
from typing import Protocol

from app.config.settings import settings
from app.ncs.records import NcsCertRecord, NcsUnitRecord

logger = logging.getLogger("myith.ncs.source")

SEED_DIR = Path(__file__).resolve().parent.parent / "data" / "ncs_seed"


class NcsSource(Protocol):
    def fetch_units(self) -> list[NcsUnitRecord]: ...
    def fetch_certifications(self) -> list[NcsCertRecord]: ...


class SeedNcsSource:
    """JSON 시드에서 읽는다. 키 없이 동작하는 기본 소스."""

    def __init__(self, seed_dir: Path = SEED_DIR) -> None:
        self._seed_dir = seed_dir

    def _load(self, filename: str) -> list[dict]:
        path = self._seed_dir / filename
        with path.open(encoding="utf-8") as f:
            return json.load(f)

    def fetch_units(self) -> list[NcsUnitRecord]:
        return [NcsUnitRecord(**row) for row in self._load("ncs_units.json")]

    def fetch_certifications(self) -> list[NcsCertRecord]:
        return [NcsCertRecord(**row) for row in self._load("ncs_certifications.json")]


class ApiNcsSource:
    """data.go.kr NCS API (I-2/I-3, https://apis.data.go.kr/B490007).

    구현 시 C-5(타임아웃·지수 백오프 재시도)로 감싼다. 일회성 배치라 서킷브레이커는
    넣지 않는다 (확정 W2 D-1). serviceKey는 로그에 마스킹한다.

    HANDOFF 아님(이 저장소 작업). 다만 아래 fetch_units 필드 매핑은 /NCS005
    응답 스키마(필드명) 샘플이 있어야 정확히 채운다 — 추측하지 않는다 (PART H).
    FallbackNcsSource로 감싸므로, 미구현 상태에서 키가 있어도 시드로 폴백하고
    배치가 죽지 않는다.
    """

    def __init__(self, service_key: str) -> None:
        self._service_key = service_key

    def fetch_units(self) -> list[NcsUnitRecord]:
        # /NCS005 능력단위분류코드 응답 필드명 확정 후 구현. 그 전엔 폴백이 받는다.
        raise NotImplementedError(
            "ApiNcsSource.fetch_units: /NCS005 응답 필드 스키마 확보 후 구현 (확정 W2 D-1). "
            "필드명을 추측하지 않는다."
        )

    def fetch_certifications(self) -> list[NcsCertRecord]:
        # 자격종목은 능력단위별(ncsClCd) 호출이다 — 커서 로더에서 단위별로 받는다 (D-3).
        raise NotImplementedError(
            "ApiNcsSource.fetch_certifications: /getNcsClCdJmList 커서 로더로 구현 예정 (D-3)."
        )


class FallbackNcsSource:
    """primary(API)가 실패하면 WARNING을 남기고 fallback(시드)로 떨어진다.

    시연 안전장치 (확정 W2 D-1). 조용히 넘어가지 않는다 — "지금 시드로 돌고 있다"가
    로그에 보여야 한다.
    """

    def __init__(self, primary: NcsSource, fallback: NcsSource) -> None:
        self._primary = primary
        self._fallback = fallback

    def fetch_units(self) -> list[NcsUnitRecord]:
        try:
            return self._primary.fetch_units()
        except Exception as e:  # noqa: BLE001 — 어떤 실패든 시드로 폴백
            logger.warning("NCS API fetch_units 실패 → 시드 폴백: %s", e)
            return self._fallback.fetch_units()

    def fetch_certifications(self) -> list[NcsCertRecord]:
        try:
            return self._primary.fetch_certifications()
        except Exception as e:  # noqa: BLE001
            logger.warning("NCS API fetch_certifications 실패 → 시드 폴백: %s", e)
            return self._fallback.fetch_certifications()


def get_ncs_source() -> NcsSource:
    """키가 있으면 API(+시드 폴백), 없으면 시드. 로더는 이 팩토리만 부르면 된다."""
    if settings.NCS_SERVICE_KEY:
        return FallbackNcsSource(
            primary=ApiNcsSource(settings.NCS_SERVICE_KEY),
            fallback=SeedNcsSource(),
        )
    return SeedNcsSource()
