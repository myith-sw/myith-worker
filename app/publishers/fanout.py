"""Worker→Core fanout 발행 (D-3). 내부 봉투를 **와이어 형식**으로 매핑한다.

🔴 와이어 형식은 CLAUDE.md D-1 문서와 다르다 (Core RabbitConfig/WorkerEventConsumer 실측):
   - eventId·eventType·traceId 는 **AMQP 헤더**로 보낸다. body가 아니다.
   - body 는 **payload 자체** — 봉투로 감싸지 않는다(`{"payload": ...}` 금지).
   - version·occurredAt 은 와이어에 없다(내부 봉투에만 있고 발신하지 않는다).

   Core WorkerEventConsumer는 헤더에서 eventType·eventId를 읽고, 둘 중 하나라도 없으면
   `"Worker event missing headers, skipping"` 로그만 남기고 **조용히 버린다**. 그리고
   roadmapId 등은 payload **루트**에서 읽으므로(`payload.has("roadmapId")`) 중첩시키지 않는다.
"""

from __future__ import annotations

import json
import logging

import aio_pika

logger = logging.getLogger("myith.publisher.fanout")


class AioPikaFanoutPublisher:
    """fanout 익스체인지 하나에 발행한다. ai_enhancement 등이 기대하는 publish(envelope) 구현."""

    def __init__(self, exchange: aio_pika.abc.AbstractExchange) -> None:
        self._exchange = exchange

    async def publish(self, envelope: dict) -> None:
        payload = envelope.get("payload") or {}
        headers = {
            "eventId": str(envelope["eventId"]),  # ★ 없으면 Core가 버린다
            "eventType": str(envelope["eventType"]),  # ★ 없으면 Core가 버린다
            "traceId": envelope.get("traceId") or "",
        }
        message = aio_pika.Message(
            body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),  # payload만
            content_type="application/json",
            headers=headers,
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        # fanout은 라우팅 키를 무시한다. Core는 인스턴스별 임시 큐를 이 익스체인지에 바인딩해 받는다.
        await self._exchange.publish(message, routing_key="")
        logger.info(
            "fanout 발행: eventType=%s eventId=%s",
            headers["eventType"],
            headers["eventId"],
        )
