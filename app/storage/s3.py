"""S3 객체 가져오기 (G-4). 업로드 문서를 fileKey로 읽는다.

자격증명은 **인스턴스 프로파일(IAM 역할)**로 자동 획득한다(C-8) — 키를 코드·env에 넣지 않는다.
boto3는 동기이므로 asyncio.to_thread로 감싼다. 크기 상한을 먼저 확인해 대용량을 막고, 버킷·키가
없거나 실패하면 None으로 degrade한다(C-3). 파일을 디스크에 쓰지 않고 메모리로만 다룬다(20GB 공유).
"""

from __future__ import annotations

import asyncio
import logging

from app.config.settings import settings

logger = logging.getLogger("myith.storage.s3")


class S3Fetcher:
    def __init__(self, bucket: str | None = None, client=None) -> None:
        self._bucket = bucket if bucket is not None else settings.S3_BUCKET
        self._client = client

    def _get_client(self):
        if self._client is None:
            import boto3

            self._client = boto3.client("s3", region_name=settings.AWS_REGION)
        return self._client

    async def fetch(self, key: str, max_bytes: int) -> bytes | None:
        if not self._bucket or not key:
            return None
        return await asyncio.to_thread(self._get, key, max_bytes)

    def _get(self, key: str, max_bytes: int) -> bytes | None:
        # get_object + 스트림 read를 한 guard로 감싼다 — 스트림 중간 실패(ReadTimeout·
        # IncompleteRead 등)도 None으로 degrade해야 파이프라인이 죽지 않는다(C-3).
        try:
            obj = self._get_client().get_object(Bucket=self._bucket, Key=key)
            size = obj.get("ContentLength")
            if size is not None and size > max_bytes:
                logger.warning("파일 상한 초과 → 스킵 (key=%s, %d>%d)", key, size, max_bytes)
                return None
            body = obj["Body"]
            try:
                data = body.read(max_bytes + 1)  # 상한+1 읽어 초과 감지
            finally:
                body.close()
        except Exception as e:  # noqa: BLE001 — 404·권한·네트워크·스트림 중단 등. 스킵(C-3).
            logger.warning("S3 조회/읽기 실패 → 스킵 (key=%s): %s", key, e)
            return None
        if len(data) > max_bytes:
            logger.warning("파일 상한 초과(스트림) → 스킵 (key=%s)", key)
            return None
        return data
