"""/health — 로컬·컨테이너 점검용. ALB 헬스체크 대상은 아니다 (O-1).

의존 대상(DB/큐)에 실제로 붙지 않는다. 기동 직후 Core 테이블이나 큐가
아직 없을 수 있고, 그것을 치명적 오류로 보지 않는다 (E-마이그레이션, D-7).
"""

from fastapi import APIRouter

from app.config.settings import settings

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "env": settings.APP_ENV,
    }
