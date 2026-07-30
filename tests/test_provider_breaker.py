"""LLM 서킷브레이커(C-5) + 개방 시 폴백(C-3). 실제 Anthropic 없이 가짜 클라이언트로 검증.

선불 $5 소진(402)·429가 연속되면 회로가 열려 즉시 CircuitOpenError → 호출부가 폴백해야 한다.
브레이커가 asyncio에서 동작하는지(과거 pybreaker NameError 회귀 방지)도 여기서 지킨다.
"""

import asyncio

import pytest

from app.competency.analyzer import extract_competencies
from app.llm import provider as provider_mod
from app.llm.provider import AnthropicLLMProvider, _build_client, _image_media_type
from app.resilience.breaker import AsyncCircuitBreaker, CircuitOpenError


def _run(coro):
    return asyncio.run(coro)


class _FakeMessages:
    def __init__(self, exc):
        self._exc = exc
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        raise self._exc


class _FakeClient:
    def __init__(self, exc):
        self.messages = _FakeMessages(exc)


def test_llm_breaker_opens_then_short_circuits_without_calling():
    breaker = AsyncCircuitBreaker(fail_max=2, reset_timeout=30, name="llm-test")
    client = _FakeClient(RuntimeError("429 rate limit"))
    provider = AnthropicLLMProvider(client, breaker=breaker)

    for _ in range(2):  # 2회 실패 → 개방
        with pytest.raises(RuntimeError):
            _run(provider.complete_json(prompt="x", schema={}, model="m", max_tokens=10))
    # 개방 후: 실제 호출 없이 CircuitOpenError
    with pytest.raises(CircuitOpenError):
        _run(provider.complete_json(prompt="x", schema={}, model="m", max_tokens=10))

    assert client.messages.calls == 2  # 개방 상태에선 messages.create를 부르지 않는다
    assert breaker.current_state == "open"


class _OpenBreakerProvider:
    """항상 CircuitOpenError를 내는 공급자(회로 개방 상황 모사)."""

    async def complete_json(self, **kwargs):
        raise CircuitOpenError("llm")


def test_extract_competencies_falls_back_to_empty_when_breaker_open():
    out = _run(
        extract_competencies(
            "React로 대시보드를 구현했다",
            [{"skillCode": "react", "skillName": "React"}],
            _OpenBreakerProvider(),
            retries=1,
        )
    )
    assert out == []  # 폴백: 파이프라인은 완주, 자가진단만으로 조립(C-3)


# ── Vision media_type: 업로드 이미지가 png가 아닐 수 있다(리뷰 high 수정) ──


def test_image_media_type_detection():
    assert _image_media_type(b"\x89PNG\r\n\x1a\n....") == "image/png"
    assert _image_media_type(b"\xff\xd8\xff\xe0....") == "image/jpeg"
    assert _image_media_type(b"RIFF\x00\x00\x00\x00WEBP....") == "image/webp"
    assert _image_media_type(b"GIF89a....") == "image/gif"


# ── 공급자 기본값: anthropic이 기본, vertex는 명시 옵트인만 (HIGH 수정 회귀) ──


def _set(monkeypatch, **kw):
    for k, v in kw.items():
        monkeypatch.setattr(provider_mod.settings, k, v)


def test_build_client_empty_provider_falls_back_to_anthropic_not_vertex(monkeypatch):
    # compose가 LLM_PROVIDER=""를 주입해도(O-3 ${VAR:-}) vertex로 새면 안 된다.
    # 유효 키가 있으면 anthropic 클라이언트가 만들어져야 한다(AI가 조용히 꺼지지 않음).
    _set(monkeypatch, LLM_PROVIDER="", LLM_API_KEY="sk-test", GCP_PROJECT_ID=None)
    client = _build_client()
    assert client is not None
    assert type(client).__name__ == "AsyncAnthropic"  # AsyncAnthropicVertex 아님


def test_build_client_none_provider_falls_back_to_anthropic(monkeypatch):
    _set(monkeypatch, LLM_PROVIDER=None, LLM_API_KEY="sk-test", GCP_PROJECT_ID=None)
    assert type(_build_client()).__name__ == "AsyncAnthropic"


def test_build_client_explicit_vertex_still_honored(monkeypatch):
    # 명시적 vertex 옵트인은 그대로 동작한다(GCP 없으면 None=비활성). 수정이 vertex 경로를 막지 않음.
    _set(monkeypatch, LLM_PROVIDER="vertex", LLM_API_KEY="sk-test", GCP_PROJECT_ID=None)
    assert _build_client() is None


def test_build_client_no_api_key_disables(monkeypatch):
    # anthropic 경로인데 키 없으면 None(규칙 폴백, C-3)
    _set(monkeypatch, LLM_PROVIDER="anthropic", LLM_API_KEY=None, GCP_PROJECT_ID=None)
    assert _build_client() is None
    assert _image_media_type(b"unknown") == "image/png"  # 기본
