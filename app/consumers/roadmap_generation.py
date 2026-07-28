"""G 교차검증 진단 컨슈머 (G-2 서술형). RoadmapGenerationRequested → CompetencyExtracted.

전송(aio-pika)과 분리된 순수 오케스트레이션 — provider·publisher·repo를 주입받아 단위 테스트한다.

흐름(D-3 진행률 + D-5/G-6 순서):
  progress 25(파싱) → LLM 역량 추출 → progress 60(증거) → **user_competency DB 쓰기(먼저)**
  → progress 90(병합) → progress 100(저장 완료) → **CompetencyExtracted 발행(그 다음)**

D-5: DB 쓰기가 발행보다 **먼저**여야 Core 정합성 스케줄러 안전망이 동작한다. 발행이 실패해도
(→ DLQ) user_competency가 있으면 Core가 그것으로 조립한다.

G-2 범위: 서술형만 — narrative{strength,difficulty} + experiences[].content 텍스트.
repoUrl·fileKey는 읽지 않는다(G-3 GitHub·G-4 PDF는 이후). LLM 실패·근거 0건이면 competencies=[]로
발행한다(D-3: 빈 배열도 발행 → Core가 자가진단만으로 폴백 조립). 이 경로는 예외를 올리지 않는다.
DB·브로커 인프라 오류만 예외로 올려 DLQ로 보낸다(재처리).
"""

from __future__ import annotations

import logging
from typing import Protocol

from app.competency.analyzer import extract_competencies
from app.config.settings import settings
from app.llm.provider import LLMProvider
from app.messaging.envelope import build_envelope
from app.pipeline.guidance import personalize_guidance, select_guidance

logger = logging.getLogger("myith.consumer.roadmap")

COMPETENCY_EXTRACTED = "CompetencyExtracted"
ROADMAP_PROGRESS = "RoadmapGenerationProgress"

# D-3 진행률 규약: (step, percent)
_STEPS = {
    "parse": 25,  # 수집/파싱
    "evidence": 60,  # 증거 분석
    "merge": 90,  # 병합
    "saved": 100,  # 저장 완료 (직후 CompetencyExtracted)
}


class FanoutPublisher(Protocol):
    async def publish(self, envelope: dict) -> None: ...


class CompetencyRepo(Protocol):
    async def load_skills(self, job_code: str, version: int | None) -> list[dict]: ...
    async def write_competencies(self, roadmap_id: int, competencies: list[dict]) -> None: ...
    async def load_guidance_templates(self, job_code: str, version: int | None) -> dict: ...
    async def write_guidance(self, roadmap_id: int, rows: list[dict]) -> None: ...


def _narrative_text(payload: dict) -> str:
    """narrative{strength,difficulty}를 한 문자열로. 층2 개인화 입력(없으면 "")."""
    narrative = payload.get("narrative")
    if not isinstance(narrative, dict):
        return ""
    parts = [str(narrative.get(k) or "").strip() for k in ("strength", "difficulty")]
    return " ".join(p for p in parts if p)


class GitHubClient(Protocol):
    async def fetch_repo_evidence(self, repo_url: str) -> str | None: ...


class DocSource(Protocol):
    async def fetch_and_parse(self, file_key: str) -> str: ...


def _gather_content(payload: dict) -> str:
    """서술형 텍스트만 모은다(G-2). narrative 객체 + experiences[].content."""
    parts: list[str] = []
    narrative = payload.get("narrative")
    if isinstance(narrative, dict):
        for key in ("strength", "difficulty"):
            val = str(narrative.get(key) or "").strip()
            if val:
                parts.append(val)
    for exp in payload.get("experiences") or []:
        if isinstance(exp, dict):
            content = str(exp.get("content") or "").strip()
            if content:
                parts.append(content)
    return "\n".join(parts)


async def _gather_all_content(
    payload: dict,
    github_client: "GitHubClient | None",
    doc_source: "DocSource | None" = None,
) -> str:
    """서술형(G-2) + GitHub 요약(G-3) + 업로드 문서(G-4)를 한 덩어리로. 같은 analyzer에 넣는다.

    experiences[]의 repoUrl·fileKey를 순회(중복 제거)해 각 근거를 붙인다. 실패·비공개·없음은
    클라이언트가 None/""을 돌려주므로 그냥 빠진다(파이프라인 안 죽음). 이 수집은 진행률
    25(수집/파싱) 안에 들어간다 — 단계를 늘리지 않는다.
    """
    parts = [_gather_content(payload)]
    seen_repo: set[str] = set()
    seen_file: set[str] = set()
    # 최대 N개만 처리(Core policy와 일치). 파일 다수 × Vision 페이지로 비용이 폭발하지 않게 상한.
    for exp in (payload.get("experiences") or [])[: settings.MAX_EXPERIENCES]:
        if not isinstance(exp, dict):
            continue
        url = exp.get("repoUrl")
        if github_client is not None and isinstance(url, str) and url and url not in seen_repo:
            seen_repo.add(url)
            text = await github_client.fetch_repo_evidence(url)
            if text:
                parts.append(text)
        file_key = exp.get("fileKey")
        if doc_source is not None and isinstance(file_key, str) and file_key and file_key not in seen_file:
            seen_file.add(file_key)
            text = await doc_source.fetch_and_parse(file_key)
            if text:
                parts.append(text)
    return "\n".join(p for p in parts if p)


async def _publish_progress(publisher, roadmap_id, step: str, trace_id) -> None:
    percent = _STEPS[step]
    env = build_envelope(
        ROADMAP_PROGRESS,
        {"roadmapId": roadmap_id, "step": step, "percent": percent},
        target_id=f"{roadmap_id}:{percent}",  # 단계별 결정론적 → 재전송 중복 방지
        trace_id=trace_id,
    )
    await publisher.publish(env)


async def handle_roadmap_generation(
    payload: dict,
    provider: LLMProvider | None,
    publisher: FanoutPublisher,
    repo: CompetencyRepo,
    *,
    github_client: GitHubClient | None = None,
    doc_source: DocSource | None = None,
    trace_id: str | None = None,
) -> dict:
    """RoadmapGenerationRequested 처리 → CompetencyExtracted 발행. 발행 봉투를 반환."""
    roadmap_id = payload.get("roadmapId")
    user_id = payload.get("userId")
    job_code = payload.get("jobCode")
    profile_version = payload.get("profileVersion")

    await _publish_progress(publisher, roadmap_id, "parse", trace_id)

    content = await _gather_all_content(payload, github_client, doc_source)  # 서술형+GitHub+문서
    skills = await repo.load_skills(job_code, profile_version)  # 닫힌 후보 집합(가드 1)
    competencies = await extract_competencies(content, skills, provider)  # 실패 시 [] (가드 5)

    await _publish_progress(publisher, roadmap_id, "evidence", trace_id)

    # D-5/G-6: DB 쓰기 먼저 (부분 upsert, 빈 배열은 no-op — 삭제 안 함)
    await repo.write_competencies(roadmap_id, competencies)

    # H-1 층2: 근거 스킬의 guidance를 narrative로 다듬어 user_quest_guidance에 저장.
    # user_competency 쓰기 직후 · CompetencyExtracted 발행 전(D-5). narrative 없으면 빈 리스트
    # → Core가 층1 수행. LLM 실패는 층1 문구로 폴백(C-3).
    templates = await repo.load_guidance_templates(job_code, profile_version)
    items = select_guidance(competencies, templates)
    guidance_rows = await personalize_guidance(items, _narrative_text(payload), provider)
    await repo.write_guidance(roadmap_id, guidance_rows)

    await _publish_progress(publisher, roadmap_id, "merge", trace_id)
    await _publish_progress(publisher, roadmap_id, "saved", trace_id)

    # CompetencyExtracted (직후). competencies 원소는 정확히 4필드(W3). 빈 배열도 발행(D-3).
    env = build_envelope(
        COMPETENCY_EXTRACTED,
        {"userId": user_id, "roadmapId": roadmap_id, "competencies": competencies},
        target_id=str(roadmap_id),  # 재발행 동일 eventId (W2 C-3)
        trace_id=trace_id,
    )
    await publisher.publish(env)
    logger.info(
        "CompetencyExtracted 발행: roadmapId=%s 근거 %d건", roadmap_id, len(competencies)
    )
    return env
