"""JobProfileBuildRequested 컨슈머 — ACK + 로그만 (확정).

시드에 job_profile 10건이 이미 있어 런타임 빌드가 불필요하다. 하지만 Core의
JobProfileRefreshScheduler·JobQueryService가 이 이벤트를 계속 발행하므로, 소비자가 없으면
큐가 쌓인다(t3.small에서 RabbitMQ와 메모리 공유 — 방치 금지). 그래서 소비·ACK만 하고 로그를 남긴다.

# TODO(F): 직무 프로필 빌드 파이프라인(F-1~F-11) 구현 시 여기서 orchestrator를 호출한다.
#   그 전까지는 빌드하지 않는다 — 시드가 진실의 원천이다.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("myith.consumer.profile_build")


async def handle_profile_build(payload: dict) -> None:
    """소비·ACK만. 예외를 던지지 않는다(던지면 DLQ로 가 재적체)."""
    logger.info(
        "JobProfileBuildRequested 수신 — 빌드 미수행(ACK+로그, 시드 사용): jobCode=%s reason=%s",
        payload.get("jobCode"),
        payload.get("reason"),
    )
