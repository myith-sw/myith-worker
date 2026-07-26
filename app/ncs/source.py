"""NCS 데이터 소스 추상화.

지금은 시드(JSON)로 채운다. NCS_SERVICE_KEY가 확보되면 ApiNcsSource를 구현해
같은 인터페이스로 교체한다 — 로더는 소스가 무엇인지 몰라도 된다 (I-2/I-3).

skill_ncs_map은 API가 없다 — NCS 정의 + 사람 검수의 큐레이션 산출물이라(PART K)
항상 시드/파일에서 읽는다. 여기 소스는 units·certifications만 추상화한다.
"""

import json
from pathlib import Path
from typing import Protocol

from app.config.settings import settings
from app.ncs.records import NcsCertRecord, NcsUnitRecord

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
    """data.go.kr NCS API (I-2/I-3). NCS_SERVICE_KEY 확보 후 구현한다.

    구현 시 C-5(타임아웃·재시도·서킷브레이커)로 감싼다. 이 저장소 작업이다
    (HANDOFF 대상 아님).
    """

    def __init__(self, service_key: str) -> None:
        self._service_key = service_key

    def fetch_units(self) -> list[NcsUnitRecord]:
        raise NotImplementedError(
            "NCS_SERVICE_KEY 확보 후 I-2 API로 구현. 그전까지는 SeedNcsSource를 쓴다."
        )

    def fetch_certifications(self) -> list[NcsCertRecord]:
        raise NotImplementedError(
            "NCS_SERVICE_KEY 확보 후 I-3 API로 구현. 그전까지는 SeedNcsSource를 쓴다."
        )


def get_ncs_source() -> NcsSource:
    """키가 있으면 API, 없으면 시드. 로더는 이 팩토리만 부르면 자동 교체된다."""
    if settings.NCS_SERVICE_KEY:
        return ApiNcsSource(settings.NCS_SERVICE_KEY)
    return SeedNcsSource()
