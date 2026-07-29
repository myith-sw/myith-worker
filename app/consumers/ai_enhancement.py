"""H-2 STAR AI 보완 컨슈머 로직 (확정 W2 C-1·C-2).

AiEnhancementRequested payload → AiEnhancementCompleted 발행. 전송(aio-pika)과 분리된 순수
오케스트레이션이라 provider·publisher를 주입받아 단위 테스트한다.

🔴 requestId는 **받은 그대로** 되돌려준다 — `aie_` 접두어를 붙이지 않는다. Core가 저장 키로
   쓰는 값은 접두어 없는 순수 UUID다(확정). 접두어를 붙이면 조회 키와 어긋나 화면에 안 뜬다.
🔴 성공·실패 모두 발행한다. FAILED를 발행하지 않으면 프론트가 영원히 폴링한다(Core 안전망 없음).
   실패 시 enhancedStar=null, feedback=[], errorCode 채움.
"""

from __future__ import annotations

import logging
from typing import Protocol

from app.llm.provider import LLMProvider
from app.llm.star_enhance import build_star_enhancement
from app.messaging.envelope import build_envelope, now_iso

logger = logging.getLogger("myith.consumer.ai_enhancement")

AI_ENHANCEMENT_COMPLETED = "AiEnhancementCompleted"


class FanoutPublisher(Protocol):
    async def publish(self, envelope: dict) -> None: ...


async def handle_ai_enhancement(
    payload: dict,
    provider: LLMProvider | None,
    publisher: FanoutPublisher,
    *,
    evidence_reader=None,
    trace_id: str | None = None,
) -> dict:
    """AiEnhancementRequested를 처리하고 AiEnhancementCompleted를 발행. 발행한 봉투를 반환.

    skillCode(nullable)가 있고 evidence_reader가 주어지면 user_competency의 evidence를 읽어 STAR
    보완의 참고로 넣는다. skillCode 없음·null·행 없음·DB 실패는 전부 **근거 없이 기존 경로**로 진행한다
    (활동형/사용자정의 퀘스트·구버전 Core 메시지 대응). evidence 조회 실패가 AI 보완을 죽이지 않는다.
    """
    request_id = payload.get("requestId")  # 순수 UUID. 접두어 없이 그대로 되돌려준다.
    roadmap_id = payload.get("roadmapId")
    quest_id = payload.get("questId")
    skill_code = payload.get("skillCode")  # nullable — 활동형/사용자정의 퀘스트, 구버전 Core엔 없음
    star = payload.get("star") or {}
    quest_context = payload.get("questContext") or payload.get("style") or ""

    # evidence 조회는 메인 try 밖에서 — 실패해도 FAILED가 아니라 근거 없이 계속(3-5).
    evidence = None
    if evidence_reader is not None and isinstance(skill_code, str) and skill_code:
        try:
            evidence = await evidence_reader(roadmap_id, skill_code)
        except Exception as e:  # noqa: BLE001 — DB 조회 실패는 삼키고 근거 없이 진행
            logger.warning("evidence 조회 실패 → 근거 없이 진행 (requestId=%s): %s", request_id, e)
            evidence = None

    status = "COMPLETED"
    error_code = None
    result: dict = {"enhancedStar": None, "feedback": [], "resumeDraft": ""}
    try:
        if provider is None:
            raise RuntimeError("LLM 공급자 비활성(폴백)")
        result = await build_star_enhancement(star, quest_context, provider, evidence=evidence)
    except Exception as e:  # noqa: BLE001 — 어떤 실패든 FAILED로 발행(무한 폴링 방지)
        status = "FAILED"
        error_code = "AI_PROVIDER_ERROR"
        logger.warning("AI 보완 실패 → FAILED 발행 (requestId=%s): %s", request_id, e)

    out_payload = {
        "requestId": request_id,  # ★ 접두어 금지, 그대로
        "roadmapId": roadmap_id,
        "questId": quest_id,
        "status": status,
        "enhancedStar": result.get("enhancedStar") if status == "COMPLETED" else None,
        "feedback": result.get("feedback", []) if status == "COMPLETED" else [],
        "resumeDraft": result.get("resumeDraft", "") if status == "COMPLETED" else "",
        "createdAt": now_iso(),
        "errorCode": error_code,
    }
    envelope = build_envelope(
        AI_ENHANCEMENT_COMPLETED,
        out_payload,
        target_id=str(request_id),  # 재발행 시 동일 eventId (W2 C-3)
        trace_id=trace_id,
    )
    await publisher.publish(envelope)
    logger.info("AiEnhancementCompleted 발행: requestId=%s status=%s", request_id, status)
    return envelope
