"""G-5 역량 추출 가드 테스트. LLM·DB 없이 순수 검증."""

import asyncio

from app.competency.analyzer import apply_guards, build_prompt, extract_competencies

SOURCE = "React로 대시보드를 구현하고 컴포넌트를 설계했다. Docker로 배포까지 진행했다."
ALLOWED = {"react", "docker", "spring"}


def _item(code, ev, conf=0.9, mastery=0.7):
    return {"skillCode": code, "evidence": ev, "confidence": conf, "mastery": mastery}


def _guard(items, conf_min=0.6, ev_max=200):
    return apply_guards(items, ALLOWED, SOURCE, conf_min=conf_min, ev_max=ev_max)


# ── 가드 1: 닫힌 후보 집합 ────────────────────────────────────────────────


def test_guard_closed_set_filters_unknown_skill():
    assert _guard([_item("python", "React로 대시보드를 구현하고")]) == []  # 목록 밖


# ── 가드 2: 근거 강제 (비었거나 원문에 없으면 폐기) ───────────────────────────


def test_guard_evidence_empty_dropped():
    assert _guard([_item("react", "")]) == []


def test_guard_evidence_not_in_source_dropped():
    assert _guard([_item("react", "Vue로 만들었다")]) == []  # 원문에 없음


def test_guard_evidence_in_source_passes():
    out = _guard([_item("react", "React로 대시보드를 구현하고")])
    assert len(out) == 1 and out[0]["skillCode"] == "react"


# ── 가드 3: 신뢰도 임계 ──────────────────────────────────────────────────


def test_guard_confidence_below_min_dropped():
    assert _guard([_item("docker", "Docker로 배포까지 진행했다", conf=0.5)]) == []
    assert len(_guard([_item("docker", "Docker로 배포까지 진행했다", conf=0.61)])) == 1


# ── 범위·중복·상한 ────────────────────────────────────────────────────────


def test_mastery_over_one_dropped():
    assert _guard([_item("react", "React로 대시보드를 구현하고", mastery=1.5)]) == []


def test_dedup_first_wins():
    items = [
        _item("react", "React로 대시보드를 구현하고", conf=0.9),
        _item("react", "컴포넌트를 설계했다", conf=0.8),
    ]
    assert len(_guard(items)) == 1


def test_evidence_capped_to_max_len():
    out = _guard([_item("react", "React로 대시보드를 구현하고")], ev_max=5)
    assert len(out[0]["evidence"]) == 5


def test_output_exactly_four_fields():
    out = _guard([_item("react", "React로 대시보드를 구현하고")])
    assert set(out[0].keys()) == {"skillCode", "mastery", "evidence", "confidence"}


# ── build_prompt: 데이터 영역 분리(C-4) ──────────────────────────────────


def test_build_prompt_wraps_data_area():
    p = build_prompt(SOURCE, [{"skillCode": "react", "skillName": "React"}])
    assert "데이터 영역 시작" in p and "데이터 영역 끝" in p
    assert "react: React" in p and SOURCE in p


# ── extract_competencies: 가드 5(폴백) + 스키마 재시도 ────────────────────


class FakeProvider:
    def __init__(self, response=None, *, raises=None):
        self._response, self._raises = response, raises
        self.calls = 0

    async def complete_json(self, *, prompt, schema, model, max_tokens):
        self.calls += 1
        if self._raises:
            raise self._raises
        return self._response


def _run(coro):
    return asyncio.run(coro)


SKILLS = [{"skillCode": "react", "skillName": "React"}]


def test_extract_provider_none_returns_empty():
    assert _run(extract_competencies(SOURCE, SKILLS, None)) == []


def test_extract_empty_content_returns_empty():
    assert _run(extract_competencies("   ", SKILLS, FakeProvider({"competencies": []}))) == []


def test_extract_empty_skillset_returns_empty():
    assert _run(extract_competencies(SOURCE, [], FakeProvider({"competencies": []}))) == []


def test_extract_total_failure_returns_empty_after_retries():
    p = FakeProvider(raises=RuntimeError("LLM down"))
    assert _run(extract_competencies(SOURCE, SKILLS, p, retries=1)) == []
    assert p.calls == 2  # 최초 + 재시도 1


def test_extract_applies_guards_on_response():
    resp = {
        "competencies": [
            {"skillCode": "react", "evidence": "React로 대시보드를 구현하고", "confidence": 0.9, "mastery": 0.7},
            {"skillCode": "python", "evidence": "React로 대시보드를 구현하고", "confidence": 0.9, "mastery": 0.7},
        ]
    }
    out = _run(extract_competencies(SOURCE, SKILLS, FakeProvider(resp)))
    assert len(out) == 1 and out[0]["skillCode"] == "react"  # python은 닫힌집합 밖
