"""G 파이프라인 DB 접근 — 스킬셋 읽기 + user_competency 쓰기.

한 클래스로 묶어 컨슈머에 주입한다(테스트는 FakeRepo). session_factory가 None이면(DB 없음)
읽기는 [], 쓰기는 no-op으로 degrade한다 — 기동·처리가 막히면 안 된다(O-3, C-3).

**부분 upsert 시맨틱(D-4):** competencies에 있는 skill_code만 갱신/삽입한다. 배열에 없는
skill_code는 "변경 없음"이지 삭제가 아니다 — 절대 DELETE하지 않는다. 빈 배열은 no-op.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.persistence.models import JobProfile, UserCompetency, UserQuestGuidance

logger = logging.getLogger("myith.competency.repo")


class CompetencyRepository:
    def __init__(self, session_factory) -> None:
        self._sf = session_factory

    async def load_skills(self, job_code: str, version: int | None) -> list[dict]:
        """job_profile.skills(닫힌 후보 집합)을 읽는다. 없으면 [] → 추출이 [] 폴백."""
        if self._sf is None or not job_code:
            return []
        async with self._sf() as session:
            stmt = select(JobProfile.skills).where(JobProfile.job_code == job_code)
            if version is not None:
                stmt = stmt.where(JobProfile.version == version)
            else:  # profileVersion 미지정이면 최신 버전
                stmt = stmt.order_by(JobProfile.version.desc())
            row = (await session.execute(stmt.limit(1))).scalar_one_or_none()
        return list(row) if row else []

    async def load_guidance_templates(
        self, job_code: str, version: int | None
    ) -> dict[str, dict]:
        """job_profile.quest_templates → {skill_code: guidance 4종 dict}. 없으면 {}."""
        if self._sf is None or not job_code:
            return {}
        async with self._sf() as session:
            stmt = select(JobProfile.quest_templates).where(JobProfile.job_code == job_code)
            if version is not None:
                stmt = stmt.where(JobProfile.version == version)
            else:
                stmt = stmt.order_by(JobProfile.version.desc())
            row = (await session.execute(stmt.limit(1))).scalar_one_or_none()
        out: dict[str, dict] = {}
        for qt in row or []:
            code = qt.get("skillCode") if isinstance(qt, dict) else None
            guidance = qt.get("guidance") if isinstance(qt, dict) else None
            if code and isinstance(guidance, dict):
                out[code] = guidance
        return out

    async def write_guidance(self, roadmap_id: int, rows: list[dict]) -> None:
        """user_quest_guidance에 부분 upsert(D-6 멱등). 빈 리스트는 no-op(Core 층1 폴백).

        rows: [{skillCode, guidance, tier}]. user_competency 쓰기 직후·발행 전에 호출한다(D-5)."""
        if self._sf is None:
            logger.warning("DB 없음 → user_quest_guidance 미기록(폴백)")
            return
        if not rows:
            return
        async with self._sf() as session:
            for r in rows:
                stmt = (
                    insert(UserQuestGuidance)
                    .values(
                        roadmap_id=roadmap_id,
                        skill_code=r["skillCode"],
                        guidance=r["guidance"],
                        tier=r["tier"],
                    )
                    .on_conflict_do_update(
                        index_elements=["roadmap_id", "skill_code"],
                        set_={"guidance": r["guidance"], "tier": r["tier"]},
                    )
                )
                await session.execute(stmt)
            await session.commit()

    async def write_competencies(self, roadmap_id: int, competencies: list[dict]) -> None:
        """user_competency에 부분 upsert(D-4). 빈 배열은 no-op(삭제 안 함)."""
        if self._sf is None:
            logger.warning("DB 없음 → user_competency 미기록(폴백)")
            return
        if not competencies:
            return
        async with self._sf() as session:
            for c in competencies:
                stmt = (
                    insert(UserCompetency)
                    .values(
                        roadmap_id=roadmap_id,
                        skill_code=c["skillCode"],
                        mastery=c["mastery"],
                        evidence=c["evidence"],
                        confidence=c["confidence"],
                    )
                    .on_conflict_do_update(
                        index_elements=["roadmap_id", "skill_code"],
                        set_={
                            "mastery": c["mastery"],
                            "evidence": c["evidence"],
                            "confidence": c["confidence"],
                        },
                    )
                )
                await session.execute(stmt)
            await session.commit()
