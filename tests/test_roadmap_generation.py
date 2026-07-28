"""G-2 로드맵 생성 컨슈머 오케스트레이션 테스트. LLM·DB·브로커 없이 주입식 검증."""

import asyncio

from app.consumers.roadmap_generation import (
    COMPETENCY_EXTRACTED,
    ROADMAP_PROGRESS,
    _gather_content,
    handle_roadmap_generation,
)

PAYLOAD = {
    "roadmapId": 42,
    "userId": 7,
    "jobCode": "backend",
    "profileVersion": 1,
    "narrative": {"strength": "React로 대시보드를 구현", "difficulty": "배포가 어려웠다"},
    "experiences": [{"content": "Docker로 배포까지 진행했다", "repoUrl": "http://x", "fileKey": "k"}],
}
SKILLS = [{"skillCode": "react", "skillName": "React"}, {"skillCode": "docker", "skillName": "Docker"}]
GOOD_RESP = {
    "competencies": [
        {"skillCode": "react", "evidence": "React로 대시보드를 구현", "confidence": 0.9, "mastery": 0.7}
    ]
}


class FakeProvider:
    def __init__(self, response):
        self._response = response

    async def complete_json(self, *, prompt, schema, model, max_tokens):
        return self._response


class FakeRepo:
    def __init__(self, skills, log):
        self._skills, self._log = skills, log
        self.written = None

    async def load_skills(self, job_code, version):
        return self._skills

    async def write_competencies(self, roadmap_id, competencies):
        self._log.append(("write", roadmap_id))
        self.written = competencies


class FakePublisher:
    def __init__(self, log):
        self._log = log
        self.published = []

    async def publish(self, envelope):
        self._log.append(("publish", envelope["eventType"]))
        self.published.append(envelope)


def _run(coro):
    return asyncio.run(coro)


def _progress(pub):
    return [e["payload"]["percent"] for e in pub.published if e["eventType"] == ROADMAP_PROGRESS]


def _extracted(pub):
    return [e for e in pub.published if e["eventType"] == COMPETENCY_EXTRACTED]


# ── 서술형만 수집 (repoUrl/fileKey 무시) ─────────────────────────────────


def test_gather_content_narrative_and_experiences_only():
    c = _gather_content(PAYLOAD)
    assert "React로 대시보드를 구현" in c and "Docker로 배포까지 진행했다" in c
    assert "http://x" not in c and "fileKey" not in c  # G-3/G-4 이후


# ── 🔴 D-5: DB 쓰기가 CompetencyExtracted 발행보다 먼저 ──────────────────


def test_db_write_before_competency_extracted():
    log = []
    repo = FakeRepo(SKILLS, log)
    pub = FakePublisher(log)
    _run(handle_roadmap_generation(PAYLOAD, FakeProvider(GOOD_RESP), pub, repo, trace_id="t"))
    write_i = next(i for i, e in enumerate(log) if e[0] == "write")
    comp_i = next(i for i, e in enumerate(log) if e == ("publish", COMPETENCY_EXTRACTED))
    assert write_i < comp_i


# ── 빈 배열도 발행 (D-3), 진행률 규약, W3 4필드 ──────────────────────────


def test_empty_competencies_still_publishes_extracted():
    pub = FakePublisher([])
    repo = FakeRepo(SKILLS, [])
    _run(handle_roadmap_generation(PAYLOAD, None, pub, repo))  # provider None → []
    ce = _extracted(pub)
    assert len(ce) == 1 and ce[0]["payload"]["competencies"] == []


def test_progress_sequence_25_60_90_100():
    pub = FakePublisher([])
    repo = FakeRepo(SKILLS, [])
    _run(handle_roadmap_generation(PAYLOAD, None, pub, repo))
    assert _progress(pub) == [25, 60, 90, 100]


def test_competency_element_exactly_four_fields():
    pub = FakePublisher([])
    repo = FakeRepo(SKILLS, [])
    _run(handle_roadmap_generation(PAYLOAD, FakeProvider(GOOD_RESP), pub, repo))
    el = _extracted(pub)[0]["payload"]["competencies"][0]
    assert set(el.keys()) == {"skillCode", "mastery", "confidence", "evidence"}  # W3


def test_extracted_payload_has_user_and_roadmap_ids():
    pub = FakePublisher([])
    repo = FakeRepo(SKILLS, [])
    _run(handle_roadmap_generation(PAYLOAD, FakeProvider(GOOD_RESP), pub, repo))
    p = _extracted(pub)[0]["payload"]
    assert p["roadmapId"] == 42 and p["userId"] == 7


def test_no_profile_skills_falls_back_to_empty():
    # 프로필 없음(load_skills []) → 추출 불가 → 빈 배열 발행(폴백)
    pub = FakePublisher([])
    repo = FakeRepo([], [])
    _run(handle_roadmap_generation(PAYLOAD, FakeProvider(GOOD_RESP), pub, repo))
    assert _extracted(pub)[0]["payload"]["competencies"] == []
