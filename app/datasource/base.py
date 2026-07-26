"""채용 데이터 소스 인터페이스 (I-1). 구현체는 바뀔 수 있고 파이프라인은 몰라야 한다.

파이프라인이 필요로 하는 4개 필드만 채워지면 어떤 소스든 동작한다:
공고 ID · 스킬 태그 · 자격요건 본문 · 신입 수용 여부.

`accepts_entry_level`은 **nullable**이다 (확정 W2 A-4). 소스가 이 정보를 주지 않으면
None으로 두고, 난이도의 S값은 scoring.py에서 중립값으로 폴백한다.

※ 실제 원티드 응답 필드는 아직 확인되지 않았다. WantedJobDataSource 구현 시 응답
  샘플을 받아 매핑한다 — 필드명을 추측하지 않는다. SeedJobDataSource로 인증키 없이
  파이프라인 전체를 테스트한다 (Step 6).
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Category:
    code: str
    name: str


@dataclass(frozen=True)
class Posting:
    posting_id: str
    skill_tags: list[str]
    requirement_text: str
    accepts_entry_level: bool | None  # None = 소스가 이 정보를 주지 않음


@dataclass(frozen=True)
class PostingPage:
    postings: list[Posting]
    next_cursor: str | None


class JobDataSource(Protocol):
    async def fetch_categories(self) -> list[Category]: ...
    async def fetch_postings(
        self, job_code: str, cursor: str | None, limit: int
    ) -> PostingPage: ...
