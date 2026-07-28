"""LLM 공급자 (I-4). Vertex 우선, anthropic 폴백. 비동기 클라이언트.

파이프라인은 공급자·모델을 몰라야 한다 → LLMProvider 뒤에 둔다. 구조화 출력은
output_config.format(json_schema)로만 강제한다. 요청 kwargs는 build_request_kwargs 한 곳에서
만들고, 미지원 파라미터는 아예 넣지 않는다.

**금지 파라미터는 전역이 아니라 모델별이다** (확정, claude-api 스킬 + 시드 가이드 AI 재확인) →
아래 UNSUPPORTED_PARAMS 표가 진실의 원천이다:
- sonnet-5/opus-5/opus-4.8: 샘플링 계열(temperature/top_p/top_k)·thinking.budget_tokens → 400.
- claude-haiku-4-5: 구세대라 temperature/top_p/top_k는 **허용**되지만 output_config.effort → 400.

따라서 H-2(STAR, haiku)는 output_config.format + max_tokens만으로 확정한다 — effort를 넣지
않는다. H-1(문구 개인화, haiku)에서 짧은 문장을 다듬을 때 temperature가 필요해지면 그때
build_request_kwargs에 파라미터를 추가하되 반드시 이 표로 검증한다.

anthropic 임포트는 지연시킨다 — 미설치·미인증이면 팩토리가 None을 돌려주고 호출부가 규칙
폴백으로 degrade한다(C-3). 어떤 LLM 실패도 파이프라인을 죽이지 않는다.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from app.config.settings import settings

logger = logging.getLogger("myith.llm")

# 모델 → 그 모델이 400을 내는 파라미터(점 표기로 중첩 표현). 새 모델이 없으면 빈 집합(허용).
UNSUPPORTED_PARAMS: dict[str, set[str]] = {
    "claude-sonnet-5": {"temperature", "top_p", "top_k", "thinking.budget_tokens"},
    "claude-opus-5": {"temperature", "top_p", "top_k", "thinking.budget_tokens"},
    "claude-opus-4-8": {"temperature", "top_p", "top_k", "thinking.budget_tokens"},
    "claude-fable-5": {"temperature", "top_p", "top_k", "thinking.budget_tokens"},
    "claude-haiku-4-5": {"output_config.effort"},  # 샘플링 계열은 허용, effort만 금지
}


def unsupported_params(model: str) -> set[str]:
    # 미지 모델(설정 오타 등)은 빈 집합 → 필터 안 함(C-3: 기동·호출이 막히면 안 된다).
    # 실제 금지 파라미터를 보내면 API가 400을 주고 서킷브레이커·폴백이 받는다.
    return UNSUPPORTED_PARAMS.get(model, set())


def build_request_kwargs(
    *, model: str, prompt: str, schema: dict, max_tokens: int
) -> dict:
    """messages.create에 넘길 kwargs를 만드는 유일한 지점. 구조화 출력만 지정한다.

    샘플링·effort 파라미터는 넣지 않는다 → 어떤 모델에서도 UNSUPPORTED_PARAMS에 걸리지 않는다.
    새 파라미터를 추가하려면 unsupported_params(model)로 반드시 검증한다.
    """
    return {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
        "output_config": {"format": {"type": "json_schema", "schema": schema}},
    }


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
        resp = await self._client.messages.create(
            **build_request_kwargs(
                model=model, prompt=prompt, schema=schema, max_tokens=max_tokens
            )
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
