"""FastAPI 앱 + 라이프사이클.

기동 실패를 만들지 않는다 (O-3): DB·큐가 없어도 앱은 뜨고 /health는 200.
로그는 stdout으로만 (PART J). 컨슈머·파이프라인은 이후 PART에서 붙는다.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.config.settings import settings

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("myith.worker")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("worker starting: app=%s env=%s", settings.APP_NAME, settings.APP_ENV)
    # 브로커·DB 연결 실패로 기동이 죽으면 안 된다 (O-3): 잡아서 로그만 남기고 /health는 200.
    runtime = None
    try:
        from app.consumers.base import setup_messaging
        from app.llm.provider import get_llm_provider

        provider = get_llm_provider()  # None이면 핸들러가 FAILED 발행/규칙 폴백 (C-3)
        runtime = await setup_messaging(provider)
    except Exception as e:  # noqa: BLE001 — 브로커 부재·연결 실패 등. 컨슈머 없이 계속.
        logger.warning("메시징 기동 실패 → 컨슈머 없이 계속 (/health는 200): %s", e)
    yield
    if runtime is not None:
        await runtime.close()
    logger.info("worker shutting down")


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)
app.include_router(health_router)
