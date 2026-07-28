"""G-4 2단계 OCR 공급자 (I-5). Google Vision. 신뢰도를 반환해야 3단 판정이 동작한다.

**자격증명(GOOGLE_APPLICATION_CREDENTIALS)이 없으면 get_ocr_provider()가 None을 돌려주고
2단계는 통째로 스킵된다** — 시연 운영 .env엔 이 값이 없어 1단계(텍스트)→3단계(Vision)로 간다.
google-cloud-vision은 동기 클라이언트라 asyncio.to_thread로 감싼다(이벤트 루프 안 막음).
"""

from __future__ import annotations

import asyncio
import logging

from app.competency.document import OcrResult
from app.config.settings import settings

logger = logging.getLogger("myith.competency.ocr")


class GoogleVisionOcr:
    def __init__(self, client) -> None:
        self._client = client

    async def extract_text(self, image: bytes) -> OcrResult | None:
        return await asyncio.to_thread(self._detect, image)

    def _detect(self, image: bytes) -> OcrResult | None:
        from google.cloud import vision

        resp = self._client.document_text_detection(image=vision.Image(content=image))
        if resp.error.message:
            logger.warning("Vision OCR 오류: %s", resp.error.message)
            return None
        annotation = resp.full_text_annotation
        text = annotation.text or ""
        confs = [p.confidence for p in annotation.pages] or [0.0]
        return OcrResult(text=text, confidence=sum(confs) / len(confs))


def get_ocr_provider() -> GoogleVisionOcr | None:
    """자격증명·SDK가 갖춰졌으면 공급자를, 아니면 None(2단계 스킵)."""
    if not settings.GOOGLE_APPLICATION_CREDENTIALS:
        logger.info("OCR 비활성: GOOGLE_APPLICATION_CREDENTIALS 없음 → 2단계 스킵 (텍스트→Vision)")
        return None
    try:
        from google.cloud import vision

        return GoogleVisionOcr(vision.ImageAnnotatorClient())
    except Exception as e:  # noqa: BLE001 — 미설치·인증 실패 등. 2단계만 스킵.
        logger.warning("OCR 클라이언트 생성 실패 → 2단계 스킵: %s", e)
        return None
