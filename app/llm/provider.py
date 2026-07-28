"""LLM 공급자 (I-4). Vertex 우선, anthropic 폴백. 비동기 클라이언트.

파이프라인은 공급자·모델을 몰라야 한다 → LLMProvider 뒤에 둔다. 구조화 출력은
output_config.format(json_schema)로만 강제한다. 금지 파라미터(I-4)는 아예 만들지 않는다 —
샘플링 계열·thinking·마지막 assistant prefill. '낮은 온도가 필요한 자리'도 출력 제약으로 표현한다.

effort는 여기서 쓰지 않는다: 경량 모델(claude-haiku-4-5)은 effort를 400으로 거부한다(확인됨).
따라서 output_config엔 format만 넣는다. sonnet 계열 전용 옵션이 필요해지면 그때 분기한다.

anthropic 임포트는 지연시킨다 — 미설치·미인증이면 팩토리가 None을 돌려주고 호출부가 규칙
폴백으로 degrade한다(C-3). 어떤 LLM 실패도 파이프라인을 죽이지 않는다.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from app.config.settings import settings

logger = logging.getLogger("myith.llm")


class LLMProvider(Protocol):
    async def complete_json(
        self, *, prompt: str, schema: dict, model: str, max_tokens: int
    ) -> dict:
        """prompt를 보내고 schema를 만족하는 JSON(dict)을 돌려준다. 실패는 예외로 올린다."""
        ...


class AnthropicLLMProvider:
    """AnthropicVertex/Anthropic 비동기 클라이언트 래퍼. 구조화 출력만 사용."""

    def __init__(self, client: Any) -> None:
        self._client = client

    async def complete_json(
        self, *, prompt: str, schema: dict, model: str, max_tokens: int
    ) -> dict:
        # 금지 파라미터(I-4)는 만들지 않는다. 구조화 출력만 지정.
        resp = await self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
        text = next(
            (b.text for b in resp.content if getattr(b, "type", None) == "text"), None
        )
        if not text:
            raise ValueError("LLM 응답에 text 블록이 없다")
        return json.loads(text)  # output_config.format이 유효 JSON을 보장


def _build_client() -> Any | None:
    provider = (settings.LLM_PROVIDER or "vertex").lower()
    try:
        if provider == "vertex":
            if not settings.GCP_PROJECT_ID:
                logger.warning("LLM 비활성: GCP_PROJECT_ID 없음 → 규칙 폴백 (C-3)")
                return None
            from anthropic import AsyncAnthropicVertex

            return AsyncAnthropicVertex(
                project_id=settings.GCP_PROJECT_ID, region=settings.GCP_REGION
            )
        if not settings.LLM_API_KEY:
            logger.warning("LLM 비활성: LLM_API_KEY 없음 → 규칙 폴백 (C-3)")
            return None
        from anthropic import AsyncAnthropic

        return AsyncAnthropic(api_key=settings.LLM_API_KEY)
    except Exception as e:  # noqa: BLE001 — 미설치·인증 등 어떤 실패든 LLM 비활성
        logger.warning("LLM 클라이언트 생성 실패 → 규칙 폴백 (C-3): %s", e)
        return None


def get_llm_provider() -> LLMProvider | None:
    """키·설정·SDK가 갖춰졌으면 공급자를, 아니면 None을 돌려준다. 호출부는 None이면 폴백한다."""
    client = _build_client()
    return AnthropicLLMProvider(client) if client is not None else None
