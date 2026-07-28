"""LLM 서킷브레이커(C-5) + 개방 시 폴백(C-3). 실제 Anthropic 없이 가짜 클라이언트로 검증.

선불 $5 소진(402)·429가 연속되면 회로가 열려 즉시 CircuitOpenError → 호출부가 폴백해야 한다.
브레이커가 asyncio에서 동작하는지(과거 pybreaker NameError 회귀 방지)도 여기서 지킨다.
"""

import asyncio

import pytest

from app.competency.analyzer import extract_competencies
from app.llm.provider import AnthropicLLMProvider
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
