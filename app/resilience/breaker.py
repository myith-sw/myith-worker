"""서킷브레이커 (C-5). 외부 API별 독립 회로. GitHub·Vision 등이 공용으로 쓴다.

연속 실패가 임계(BREAKER_FAIL_MAX)를 넘으면 회로를 열어, 장애 대상을 계속 두드리지 않고
즉시 CircuitOpenError를 낸다 → 호출부가 폴백/스킵한다(C-3). 개방 후 BREAKER_RESET_SEC가
지나면 반개방으로 한 번 시도한다. async 호출은 `breaker.call_async(coro_fn, *args)`로 감싼다.

**pybreaker를 쓰지 않는다:** pybreaker의 call_async는 Tornado `gen.coroutine` 기반이라 순수
asyncio에서 `NameError: gen`으로 죽는다(확인됨). 우리 런타임은 asyncio이므로 최소 구현을 둔다.

**무엇을 실패로 셀지는 호출부가 정한다:** '스킵해도 되는 것'(404·비공개)은 예외를 던지지 말고
정상 반환(None)해 회로에 영향을 주지 않게 하고, '장애'(타임아웃·5xx·429)만 예외로 올린다.
"""

from __future__ import annotations

import time
from typing import Awaitable, Callable

from app.config.settings import settings


class CircuitOpenError(Exception):
    """회로가 열려 있어 호출을 건너뛴다."""


class AsyncCircuitBreaker:
    def __init__(self, *, fail_max: int, reset_timeout: float, name: str, clock=time.monotonic):
        self._fail_max = fail_max
        self._reset_timeout = reset_timeout
        self.name = name
        self._clock = clock
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def current_state(self) -> str:
        """'closed' | 'open' | 'half-open' (pybreaker와 동일 문자열)."""
        if self._opened_at is None:
            return "closed"
        if self._clock() - self._opened_at >= self._reset_timeout:
            return "half-open"
        return "open"

    async def call_async(self, func: Callable[..., Awaitable], *args, **kwargs):
        if self.current_state == "open":
            raise CircuitOpenError(self.name)
        try:
            result = await func(*args, **kwargs)
        except Exception:  # noqa: BLE001 — CancelledError(BaseException)는 세지 않는다
            # 취소(종료·재연결)는 장애가 아니다 → 카운트 오염 방지. 그대로 전파.
            self._failures += 1
            if self._failures >= self._fail_max:
                self._opened_at = self._clock()  # (재)개방, 타이머 재장전
            raise
        self._failures = 0  # 성공 → 회로 닫힘
        self._opened_at = None
        return result


_breakers: dict[str, AsyncCircuitBreaker] = {}


def get_breaker(name: str) -> AsyncCircuitBreaker:
    """이름별 서킷브레이커(프로세스당 1개, 재사용)."""
    breaker = _breakers.get(name)
    if breaker is None:
        breaker = AsyncCircuitBreaker(
            fail_max=settings.BREAKER_FAIL_MAX,
            reset_timeout=settings.BREAKER_RESET_SEC,
            name=name,
        )
        _breakers[name] = breaker
    return breaker
