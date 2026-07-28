"""RabbitMQ 전송·소비 배선 (D-2, D-6, D-7, PART J).

토폴로지는 Core RabbitConfig.java와 **정확히** 일치해야 한다 — 익스체인지 속성이 한 글자라도
다르면 PRECONDITION_FAILED(406)로 채널이 즉사한다. 작업 큐·DLQ는 Worker가 선언·소유한다
(Core는 작업 큐를 선언하지 않는다). Core→Worker 바인딩 라우팅 키 = eventType 문자열 그대로.

🔴 수신 봉투는 CLAUDE.md D-1 문서와 다르다 (Core OutboxRelayScheduler 실측):
   eventId·eventType·traceId 는 **AMQP 헤더**, body 는 **payload 자체**(껍데기 없음).
   `json.loads(body)["eventId"]`는 KeyError다 — 반드시 헤더에서 꺼낸다. 필수 헤더가 없으면 DLQ.

멱등(D-6): 수신 eventId를 worker_processed_event에 **INSERT-선점**한다(동시 수신 대비, DB 고유
제약으로만). 위반이면 이미 처리된 것 → ACK 후 skip. **성공 경로는 선점이 남아 중복을 막는다.**

**선점 해제(보상):** dispatch가 던지면(사실상 브로커 발행 실패뿐 — handle_ai_enhancement는
LLM 실패에도 FAILED를 발행하고 정상 반환한다) 선점을 **삭제**하고 DLQ로 보낸다. 그래야 DLQ
재처리 때 다시 시도돼 H-2의 "FAILED 항상 발행"이 발행 실패 경로에서도 지켜진다 — 선점을 남기면
재처리가 중복으로 스킵돼 COMPLETED도 FAILED도 영영 안 나가고 프론트가 무한 폴링한다
(AiEnhancement엔 Core 안전망이 없다). 재발행 eventId가 결정론적이라(W2 C-3) 재시도가 중복
발행돼도 Core가 접는다.
"""

from __future__ import annotations

import json
import logging
import uuid as _uuid

import aio_pika
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from app.config.settings import settings
from app.consumers.ai_enhancement import handle_ai_enhancement
from app.consumers.profile_build import handle_profile_build
from app.llm.provider import LLMProvider
from app.persistence.database import get_async_sessionmaker
from app.persistence.models import WorkerProcessedEvent
from app.publishers.fanout import AioPikaFanoutPublisher

logger = logging.getLogger("myith.consumer.base")

# Core→Worker 바인딩. 라우팅 키(=eventType) → (큐 설정 이름, 핸들러 종류).
# roadmap-generation은 우선순위 2에서 추가한다 — 지금 선언하면 소비자 없이 durable 큐가
# 쌓인다. 미바인딩이면 Core 발행은 topic 익스체인지에서 unroutable로 버려지고, Core의
# ConsistencyScheduler(60초) 안전망이 자가진단 폴백으로 로드맵을 완성한다(D-5).
_AI = "AiEnhancementRequested"
_PROFILE = "JobProfileBuildRequested"


def _hdr(message: aio_pika.abc.AbstractIncomingMessage, key: str) -> str | None:
    """AMQP 헤더를 문자열로. 없으면 None."""
    headers = message.headers or {}
    v = headers.get(key)
    if v is None:
        return None
    return v.decode() if isinstance(v, bytes) else str(v)


async def _claim_event(session_factory, event_id: str) -> bool:
    """eventId를 선점(INSERT). True=신규(처리 진행), False=중복(이미 처리).

    session_factory가 None(DATABASE_URL 없음)이면 멱등을 건너뛰고 처리한다(기동 성공, O-3).
    eventId가 UUID가 아니면(계약 위반) 멱등만 생략하고 처리한다 — 컬럼이 UUID형이라 저장 불가.
    """
    if session_factory is None:
        return True
    try:
        eid = _uuid.UUID(str(event_id))
    except ValueError:
        logger.warning("eventId가 UUID 아님 → 멱등 생략, 처리 진행: %s", event_id)
        return True
    async with session_factory() as session:
        session.add(WorkerProcessedEvent(event_id=eid))
        try:
            await session.commit()
            return True
        except IntegrityError:
            await session.rollback()
            return False


async def _release_event(session_factory, event_id: str) -> None:
    """선점 해제(보상). dispatch 실패 시 호출 → DLQ 재처리가 다시 시도 가능해진다.
    실패해도 삼킨다(치명적 아님 — 최악의 경우 재처리가 중복으로 스킵될 뿐)."""
    if session_factory is None:
        return
    try:
        eid = _uuid.UUID(str(event_id))
    except ValueError:
        return
    try:
        async with session_factory() as session:
            await session.execute(
                delete(WorkerProcessedEvent).where(WorkerProcessedEvent.event_id == eid)
            )
            await session.commit()
    except Exception:  # noqa: BLE001 — DB 일시 장애 등. 재처리 시 중복 스킵 가능성만 남는다.
        logger.warning("선점 해제 실패(재처리 시 중복으로 스킵될 수 있음): %s", event_id)


async def _safe_reject(message: aio_pika.abc.AbstractIncomingMessage) -> None:
    """reject(requeue=False)로 DLQ 전송. 채널이 이미 닫혔으면 삼킨다."""
    try:
        await message.reject(requeue=False)
    except Exception:  # noqa: BLE001
        logger.warning("reject 실패(채널 상태 확인)")


async def _dispatch(event_type, payload, provider, publisher, trace_id) -> None:
    if event_type == _AI:
        await handle_ai_enhancement(payload, provider, publisher, trace_id=trace_id)
    elif event_type == _PROFILE:
        await handle_profile_build(payload)
    else:  # 바인딩상 도달 불가. 방어적으로 로그만 남기고 ACK(정상 반환).
        logger.warning("미지원 eventType, ACK+무시: %s", event_type)


def _make_handler(session_factory, provider: LLMProvider | None, publisher):
    async def on_message(message: aio_pika.abc.AbstractIncomingMessage) -> None:
        # 수동 ack/reject: 성공/중복=ACK, 헤더누락·처리실패=DLQ(reject requeue=False).
        event_id = _hdr(message, "eventId")
        event_type = _hdr(message, "eventType")
        trace_id = _hdr(message, "traceId")
        if not event_id or not event_type:  # D-1: 필수 헤더 없으면 DLQ
            logger.warning("필수 헤더 누락(eventId/eventType) → DLQ")
            await _safe_reject(message)
            return
        if not await _claim_event(session_factory, event_id):  # D-6 멱등: 선점(중복 차단)
            logger.info("중복 수신 → ACK+skip: eventId=%s", event_id)
            await message.ack()
            return
        try:
            payload = json.loads(message.body)  # body = payload 자체(껍데기 없음)
            await _dispatch(event_type, payload, provider, publisher, trace_id)
            await message.ack()
        except Exception:  # noqa: BLE001 — 어떤 처리 실패든 원본 보존 위해 DLQ로
            # 보상: 선점 해제 → DLQ 재처리 시 재시도 가능(H-2 FAILED-always 보존).
            logger.exception("메시지 처리 실패 → 선점 해제 후 DLQ")
            await _release_event(session_factory, event_id)
            await _safe_reject(message)

    return on_message


class MessagingRuntime:
    """연결 수명 관리. lifespan 종료 시 close()."""

    def __init__(self, connection: aio_pika.abc.AbstractRobustConnection) -> None:
        self._connection = connection

    async def close(self) -> None:
        await self._connection.close()


async def setup_messaging(provider: LLMProvider | None) -> MessagingRuntime:
    """브로커 연결 → 익스체인지·큐·DLQ 선언 → 소비 시작. 연결 핸들을 돌려준다.

    실패는 호출부(main lifespan)가 잡아 비치명적으로 처리한다(O-3) — 여기서 삼키지 않는다.
    """
    connection = await aio_pika.connect_robust(
        host=settings.RABBITMQ_HOST,
        port=settings.RABBITMQ_PORT,
        login=settings.RABBITMQ_USER or "guest",
        password=settings.RABBITMQ_PASSWORD or "guest",
    )
    try:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=settings.RABBITMQ_PREFETCH)  # 백프레셔 (PART J)

        # 익스체인지 — 속성은 Core와 반드시 일치(불일치=406). durable=True, auto_delete=False.
        core_events = await channel.declare_exchange(
            settings.RABBITMQ_CORE_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
        )
        worker_fanout = await channel.declare_exchange(
            settings.RABBITMQ_WORKER_FANOUT, aio_pika.ExchangeType.FANOUT, durable=True
        )

        # DLQ — Worker 소유. 작업 큐는 기본 익스체인지("")로 DLQ에 dead-letter한다.
        await channel.declare_queue(settings.RABBITMQ_DLQ, durable=True)
        dlq_args = {
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": settings.RABBITMQ_DLQ,
        }

        session_factory = get_async_sessionmaker()
        publisher = AioPikaFanoutPublisher(worker_fanout)
        handler = _make_handler(session_factory, provider, publisher)

        # AI 보완 (실 핸들러) — 우선순위 1
        ai_queue = await channel.declare_queue(
            settings.RABBITMQ_QUEUE_AI_ENHANCEMENT, durable=True, arguments=dlq_args
        )
        await ai_queue.bind(core_events, routing_key=_AI)
        await ai_queue.consume(handler)

        # 프로필 빌드 (ACK+로그) — 큐 적체 방지 + 관측
        pb_queue = await channel.declare_queue(
            settings.RABBITMQ_QUEUE_PROFILE_BUILD, durable=True, arguments=dlq_args
        )
        await pb_queue.bind(core_events, routing_key=_PROFILE)
        await pb_queue.consume(handler)
    except Exception:
        # 선언 실패(406 등) 시 연결을 닫는다 — 안 그러면 main이 핸들을 못 받아(runtime=None)
        # RobustConnection의 백그라운드 태스크·소켓이 프로세스 내내 누수된다.
        await connection.close()
        raise

    logger.info(
        "메시징 소비 시작: %s, %s → fanout=%s (provider=%s)",
        settings.RABBITMQ_QUEUE_AI_ENHANCEMENT,
        settings.RABBITMQ_QUEUE_PROFILE_BUILD,
        settings.RABBITMQ_WORKER_FANOUT,
        "on" if provider is not None else "off(폴백)",
    )
    return MessagingRuntime(connection)
