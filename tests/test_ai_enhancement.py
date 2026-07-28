"""AiEnhancement 컨슈머 로직 + 봉투 테스트. DB·브로커·실제 LLM 없이 순수 검증."""

import asyncio

import pytest

from app.consumers.ai_enhancement import handle_ai_enhancement
from app.consumers.profile_build import handle_profile_build
from app.messaging.envelope import build_envelope, deterministic_event_id

REQ = {
    "requestId": "550e8400-e29b-41d4-a716-446655440000",  # 접두어 없는 순수 UUID
    "questId": 5,
    "roadmapId": 1,
    "userId": 1,
    "star": {"situation": "동아리 활동", "task": "발표 준비", "action": "자료를 정리해 발표했다", "result": "좋은 반응"},
}

GOOD = {
    "enhancedStar": {
        "situation": "동아리에서 꾸준히 활동하며",
        "task": "핵심 발표를 맡아",
        "action": "자료를 체계적으로 정리해 발표했다",
        "result": "동료들에게 좋은 반응을 얻었다",
    },
    "feedback": [{"field": "result", "issue": "정량화 부족", "suggestion": "수치로"}],
    "resumeDraft": "동아리 발표를 주도한 경험",
}


class FakeProvider:
    def __init__(self, response=None, *, raises=None):
        self._response, self._raises = response, raises

    async def complete_json(self, *, prompt, schema, model, max_tokens):
        if self._raises:
            raise self._raises
        return self._response


class FakePublisher:
    def __init__(self):
        self.published = []

    async def publish(self, envelope):
        self.published.append(envelope)


def _run(coro):
    return asyncio.run(coro)


# ── 🔴 requestId 그대로 되돌려주기 (aie_ 접두어 금지) ───────────────────────


def test_request_id_returned_verbatim_without_prefix():
    pub = FakePublisher()
    env = _run(handle_ai_enhancement(REQ, FakeProvider(GOOD), pub))
    rid = env["payload"]["requestId"]
    assert rid == REQ["requestId"]  # 그대로
    assert not rid.startswith("aie_")  # 접두어 안 붙음
    assert env["payload"]["roadmapId"] == 1  # SSE 라우팅 필수 필드


def test_success_publishes_completed_with_enhanced_star():
    pub = FakePublisher()
    env = _run(handle_ai_enhancement(REQ, FakeProvider(GOOD), pub))
    assert len(pub.published) == 1
    p = env["payload"]
    assert p["status"] == "COMPLETED"
    assert p["enhancedStar"]["action"]
    assert p["errorCode"] is None


# ── 🔴 실패해도 반드시 FAILED 발행 (무한 폴링 방지) ─────────────────────────


def test_llm_failure_publishes_failed():
    pub = FakePublisher()
    env = _run(handle_ai_enhancement(REQ, FakeProvider(raises=RuntimeError("down")), pub))
    p = env["payload"]
    assert len(pub.published) == 1  # 실패도 발행됨
    assert p["status"] == "FAILED"
    assert p["errorCode"] == "AI_PROVIDER_ERROR"
    assert p["enhancedStar"] is None and p["feedback"] == []
    assert p["requestId"] == REQ["requestId"]  # 실패 봉투도 requestId 유지


def test_provider_none_publishes_failed_not_crash():
    pub = FakePublisher()
    env = _run(handle_ai_enhancement(REQ, None, pub))  # LLM 비활성
    assert env["payload"]["status"] == "FAILED"
    assert len(pub.published) == 1


def test_fabrication_stays_completed_with_null_enhanced_star():
    resp = dict(GOOD)
    resp["enhancedStar"] = {**GOOD["enhancedStar"], "action": "React와 Redux로 50% 개선했다"}
    pub = FakePublisher()
    env = _run(handle_ai_enhancement(REQ, FakeProvider(resp), pub))
    p = env["payload"]
    assert p["status"] == "COMPLETED"  # 실패 아님
    assert p["enhancedStar"] is None  # 날조 → null
    assert p["feedback"]  # feedback은 유지


# ── eventId 결정론 (재발행 시 동일) + requestId와 다른 값 ────────────────────


def test_event_id_deterministic_across_republish():
    env1 = _run(handle_ai_enhancement(REQ, FakeProvider(GOOD), FakePublisher()))
    env2 = _run(handle_ai_enhancement(REQ, FakeProvider(GOOD), FakePublisher()))
    assert env1["eventId"] == env2["eventId"]  # 같은 requestId → 같은 eventId
    assert env1["eventId"] != REQ["requestId"]  # eventId ≠ requestId


def test_envelope_shape_and_trace_propagation():
    env = build_envelope("X", {"a": 1}, target_id="t1", trace_id="trace-123")
    assert env["eventType"] == "X" and env["version"] == 1
    assert env["traceId"] == "trace-123"
    assert env["payload"] == {"a": 1}
    assert env["eventId"] == deterministic_event_id("X", "t1")


# ── profile_build: ACK+로그만, 예외 없음 ────────────────────────────────────


def test_profile_build_handle_is_noop_without_exception():
    # 예외를 던지지 않아야 한다(던지면 DLQ 재적체)
    _run(handle_profile_build({"jobCode": "backend", "reason": "scheduled"}))
