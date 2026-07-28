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

import base64
import json
import logging
from typing import Any, Protocol

from app.config.settings import settings
from app.resilience.breaker import get_breaker

logger = logging.getLogger("myith.llm")

# 모델 → 그 모델이 400을 내는 파라미터(점 표기로 중첩 표현). 새 모델이 없으면 빈 집합(허용).
UNSUPPORTED_PARAMS: dict[str, set[str]] = {
    "claude-sonnet-5": {"temperature", "top_p", "top_k", "thinking.budget_tokens"},
    "claude-opus-5": {"temperature", "top_p", "top_k", "thinking.budget_tokens"},
    "claude-opus-4-8": {"temperature", "top_p", "top_k", "thinking.budget_tokens"},
    "claude-fable-5": {"temperature", "top_p", "top_k", "thinking.budget_tokens"},
    "claude-haiku-4-5": {"output_config.effort"},  # 샘플링 계열은 허용, effort만 금지
}


def _image_media_type(data: bytes) -> str:
    """매직바이트로 이미지 MIME 판별(Anthropic 지원: png/jpeg/gif/webp). 기본 png."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return "image/png"


def unsupported_params(model: str) -> set[str]:
    # 미지 모델(설정 오타 등)은 빈 집합 → 필터 안 함(C-3: 기동·호출이 막히면 안 된다).
    # 실제 금지 파라미터를 보내면 API가 400을 주고 서킷브레이커·폴백이 받는다.
    return UNSUPPORTED_PARAMS.get(model, set())


def build_request_kwargs(
    *,
    model: str,
    prompt: str,
    schema: dict,
    max_tokens: int,
    effort: str | None = None,
    thinking_disabled: bool = False,
) -> dict:
    """messages.create에 넘길 kwargs를 만드는 유일한 지점. 구조화 출력만 기본 지정한다.

    effort는 sonnet-5+ 계열에서만 허용된다(haiku는 400, UNSUPPORTED_PARAMS 참조) — 호출부가
    모델에 맞게만 넘긴다. thinking_disabled는 H-1 층2 확정 사양. 샘플링 파라미터는 넣지 않는다.
    """
    output_config: dict = {"format": {"type": "json_schema", "schema": schema}}
    if effort:
        output_config["effort"] = effort
    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
        "output_config": output_config,
    }
    if thinking_disabled:
        kwargs["thinking"] = {"type": "disabled"}
    return kwargs


class LLMProvider(Protocol):
    async def complete_json(
        self,
        *,
        prompt: str,
        schema: dict,
        model: str,
        max_tokens: int,
        effort: str | None = None,
        thinking_disabled: bool = False,
    ) -> dict:
        """prompt를 보내고 schema를 만족하는 JSON(dict)을 돌려준다. 실패는 예외로 올린다."""
        ...

    async def complete_with_images(
        self, *, prompt: str, images: list[bytes], schema: dict, model: str, max_tokens: int
    ) -> dict:
        """이미지 + prompt를 보내고 schema JSON을 돌려준다(G-4 Vision). 실패는 예외로 올린다."""
        ...


class AnthropicLLMProvider:
    """AnthropicVertex/Anthropic 비동기 클라이언트 래퍼. 구조화 출력만 사용.

    서킷브레이커(C-5): 연속 실패(429·402 credit_balance_too_low·5xx·타임아웃)가 임계를 넘으면
    회로를 열어 즉시 CircuitOpenError를 낸다 → 호출부(extract_competencies/star_enhance)가
    규칙 폴백/FAILED로 degrade한다(C-3). 선불 $5 소진 시 이 경로가 실제로 돈다.
    """

    def __init__(self, client: Any, *, breaker=None) -> None:
        self._client = client
        self._breaker = breaker or get_breaker("llm")

    async def complete_json(
        self,
        *,
        prompt: str,
        schema: dict,
        model: str,
        max_tokens: int,
        effort: str | None = None,
        thinking_disabled: bool = False,
    ) -> dict:
        resp = await self._breaker.call_async(
            self._client.messages.create,
            **build_request_kwargs(
                model=model,
                prompt=prompt,
                schema=schema,
                max_tokens=max_tokens,
                effort=effort,
                thinking_disabled=thinking_disabled,
            ),
        )
        text = next(
            (b.text for b in resp.content if getattr(b, "type", None) == "text"), None
        )
        if not text:
            raise ValueError("LLM 응답에 text 블록이 없다")
        return json.loads(text)  # output_config.format이 유효 JSON을 보장

    async def complete_with_images(
        self, *, prompt: str, images: list[bytes], schema: dict, model: str, max_tokens: int
    ) -> dict:
        # 이미지 블록 + 텍스트. 금지 파라미터 없이 구조화 출력만(같은 브레이커로 감쌈).
        # media_type은 매직바이트로 판별 — PDF 렌더는 PNG지만 업로드 이미지는 jpg/webp일 수 있다.
        content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": _image_media_type(img),
                    "data": base64.b64encode(img).decode(),
                },
            }
            for img in images
        ]
        content.append({"type": "text", "text": prompt})
        resp = await self._breaker.call_async(
            self._client.messages.create,
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": content}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
        text = next(
            (b.text for b in resp.content if getattr(b, "type", None) == "text"), None
        )
        if not text:
            raise ValueError("Vision 응답에 text 블록이 없다")
        return json.loads(text)


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
