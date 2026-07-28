"""guidance_tier 경계값 검증 (확정 W2 B-1) + H-1 층2 개인화. 실제 LLM 없이 검증."""

import asyncio

import pytest

from app.pipeline.guidance import (
    GUIDANCE_TIERS,
    guidance_tier,
    personalize_guidance,
    select_guidance,
)


def _run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize(
    "mastery,expected",
    [
        (0.0, "none"),
        (0.32, "none"),
        (0.33, "aware"),
        (0.65, "aware"),
        (0.66, "experienced"),
        (0.99, "experienced"),
        (1.0, "proficient"),
    ],
)
def test_guidance_tier_boundaries(mastery, expected):
    assert guidance_tier(mastery) == expected


def test_tiers_are_four_ordered():
    assert GUIDANCE_TIERS == ("none", "aware", "experienced", "proficient")


def test_experienced_and_proficient_not_merged():
    # 0.66과 1.0은 둘 다 ALREADY_KNOWN이지만 안내가 다르다.
    assert guidance_tier(0.66) != guidance_tier(1.0)


# ── 층2 개인화 (H-1, 확정 W-H1-C) ──────────────────────────────────────────

TEMPLATES = {
    "git": {"none": "gn", "aware": "ga", "experienced": "ge", "proficient": "gp"},
    "react": {"none": "rn", "aware": "ra", "experienced": "re", "proficient": "rp"},
}
ITEMS = [
    {"skillCode": "git", "tier": "experienced", "base": "ge"},
    {"skillCode": "react", "tier": "none", "base": "rn"},
]


class FakeProvider:
    def __init__(self, response=None, *, raises=None):
        self._response, self._raises = response, raises
        self.calls = 0
        self.last = {}

    async def complete_json(self, *, prompt, schema, model, max_tokens, effort=None, thinking_disabled=False):
        self.calls += 1
        self.last = {"model": model, "max_tokens": max_tokens, "effort": effort, "thinking": thinking_disabled}
        if self._raises:
            raise self._raises
        return self._response


def test_select_guidance_picks_tier_and_excludes_unmapped():
    comps = [
        {"skillCode": "git", "mastery": 0.7},  # experienced → ge
        {"skillCode": "react", "mastery": 0.2},  # none → rn
        {"skillCode": "unknown", "mastery": 0.9},  # 템플릿 없음 → 제외
    ]
    items = select_guidance(comps, TEMPLATES)
    assert {i["skillCode"]: (i["tier"], i["base"]) for i in items} == {
        "git": ("experienced", "ge"),
        "react": ("none", "rn"),
    }


def test_no_narrative_returns_empty():
    assert _run(personalize_guidance(ITEMS, "", FakeProvider({"refined": []}))) == []


def test_disabled_does_not_call_llm():
    p = FakeProvider({"refined": []})
    assert _run(personalize_guidance(ITEMS, "경험 서술", p, enabled=False)) == []
    assert p.calls == 0  # 호출 자체를 안 한다


def test_llm_success_refines_keeps_tier_and_confirmed_params():
    resp = {"refined": [{"skillCode": "git", "guidance": "다듬은 git"}, {"skillCode": "react", "guidance": "다듬은 react"}]}
    p = FakeProvider(resp)
    out = _run(personalize_guidance(ITEMS, "경험 서술", p))
    assert out == [
        {"skillCode": "git", "guidance": "다듬은 git", "tier": "experienced"},
        {"skillCode": "react", "guidance": "다듬은 react", "tier": "none"},
    ]
    assert p.last == {"model": "claude-sonnet-5", "max_tokens": 300, "effort": "low", "thinking": True}


def test_missing_skill_in_response_uses_layer1_base():
    resp = {"refined": [{"skillCode": "git", "guidance": "다듬은 git"}]}  # react 누락
    out = _run(personalize_guidance(ITEMS, "경험", FakeProvider(resp)))
    assert {o["skillCode"]: o["guidance"] for o in out} == {"git": "다듬은 git", "react": "rn"}


def test_llm_failure_falls_back_to_layer1():
    out = _run(personalize_guidance(ITEMS, "경험", FakeProvider(raises=RuntimeError("boom"))))
    assert out == [
        {"skillCode": "git", "guidance": "ge", "tier": "experienced"},
        {"skillCode": "react", "guidance": "rn", "tier": "none"},
    ]


def test_provider_none_and_no_items_fall_back():
    out = _run(personalize_guidance(ITEMS, "경험", None))
    assert out[0]["guidance"] == "ge" and out[0]["tier"] == "experienced"  # 층1
    assert _run(personalize_guidance([], "경험", FakeProvider({"refined": []}))) == []


@pytest.mark.parametrize(
    "bad",
    [
        {"refined": [{"guidance": "x"}]},  # skillCode 누락
        {"wrong": "shape"},  # refined 키 없음
        {"refined": "notalist"},  # refined가 리스트 아님
        {"refined": [123, None]},  # 원소가 dict 아님
        ["top", "level", "array"],  # 최상위가 배열
        None,  # null
    ],
)
def test_schema_nonconforming_response_falls_back_to_layer1(bad):
    # 유효 JSON이지만 스키마 이탈 → 예외로 죽지 않고 층1 문구 그대로(C-3)
    out = _run(personalize_guidance(ITEMS, "경험", FakeProvider(bad)))
    assert out == [
        {"skillCode": "git", "guidance": "ge", "tier": "experienced"},
        {"skillCode": "react", "guidance": "rn", "tier": "none"},
    ]
