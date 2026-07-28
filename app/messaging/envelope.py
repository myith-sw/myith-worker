"""메시지 봉투 (D-1). 발신 봉투 조립 + 결정론적 eventId.

Core는 AiEnhancementCompleted·CompetencyExtracted·JobProfileBuilt 수신 시 봉투 eventId를
자기 processed_event에 저장해 멱등 처리한다(확정 W2 C-3). 따라서 **재발행 시 같은 eventId**를
써야 한다 — (이벤트종류 + 대상ID)로 결정론적으로 만든다. requestId(Core가 준 값)와
eventId(우리가 만드는 봉투 ID)는 다른 값이다.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

# Worker 발행 이벤트용 고정 네임스페이스. 재발행 멱등의 근거라 절대 바꾸지 않는다.
_WORKER_EVENT_NS = uuid.UUID("6f1d2c3a-0b7e-5a4c-9f10-8a2b7c1d0e00")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def deterministic_event_id(event_type: str, target_id: str) -> str:
    """(이벤트종류 + 대상ID)로 안정적인 UUID. 재발행 시 동일값 → Core 멱등 (W2 C-3)."""
    return str(uuid.uuid5(_WORKER_EVENT_NS, f"{event_type}:{target_id}"))


def build_envelope(
    event_type: str,
    payload: dict,
    *,
    target_id: str,
    trace_id: str | None = None,
    version: int = 1,
) -> dict:
    """D-1 봉투. eventId는 target_id 기준 결정론적. traceId는 수신값을 이어준다."""
    return {
        "eventId": deterministic_event_id(event_type, target_id),
        "eventType": event_type,
        "version": version,
        "traceId": trace_id or str(uuid.uuid4()),
        "occurredAt": now_iso(),
        "payload": payload,
    }
