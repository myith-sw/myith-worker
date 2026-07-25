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
    # 여기서 DB·큐에 붙지 않는다. 연결 실패로 기동이 죽으면 안 된다 (O-3).
    # 컨슈머 기동은 메시징 PART(8번)에서 추가한다.
    yield
    logger.info("worker shutting down")


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)
app.include_router(health_router)
