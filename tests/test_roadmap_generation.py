"""G-2 로드맵 생성 컨슈머 오케스트레이션 테스트. LLM·DB·브로커 없이 주입식 검증."""

import asyncio

from app.consumers.roadmap_generation import (
    COMPETENCY_EXTRACTED,
    ROADMAP_PROGRESS,
    _gather_all_content,
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

    async def complete_json(self, *, prompt, schema, model, max_tokens, system=None, effort=None, thinking_disabled=False):
        return self._response


class FakeRepo:
    def __init__(self, skills, log, templates=None):
        self._skills, self._log = skills, log
        self._templates = templates or {}
        self.written = None
        self.guidance_written = None

    async def load_skills(self, job_code, version):
        return self._skills

    async def write_competencies(self, roadmap_id, competencies):
        self._log.append(("write", roadmap_id))
        self.written = competencies

    async def load_guidance_templates(self, job_code, version):
        return self._templates

    async def write_guidance(self, roadmap_id, rows):
        self._log.append(("write_guid", roadmap_id))
        self.guidance_written = rows


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


# ── G-3: GitHub 저장소 요약이 같은 analyzer로 흘러가는지 ────────────────────


class FakeGitHub:
    def __init__(self, mapping):
        self._mapping = mapping
        self.calls = []

    async def fetch_repo_evidence(self, repo_url):
        self.calls.append(repo_url)
        return self._mapping.get(repo_url)


def test_gather_all_content_appends_repo_and_dedups():
    payload = {
        "narrative": {"strength": "서술 강점", "difficulty": ""},
        "experiences": [
            {"content": "직접 만든 것", "repoUrl": "https://github.com/o/r1"},
            {"repoUrl": "https://github.com/o/r1"},  # 중복 → 1회만
            {"repoUrl": "https://github.com/o/r2"},  # None 반환 → 빠짐
        ],
    }
    gh = FakeGitHub({"https://github.com/o/r1": "[GitHub o/r1] React 구현", "https://github.com/o/r2": None})
    content = _run(_gather_all_content(payload, gh))
    assert "서술 강점" in content and "직접 만든 것" in content
    assert "[GitHub o/r1] React 구현" in content
    assert gh.calls == ["https://github.com/o/r1", "https://github.com/o/r2"]  # r1 dedup


def test_gather_all_content_none_client_is_narrative_only():
    content = _run(_gather_all_content(PAYLOAD, None))
    assert "http://x" not in content  # repoUrl 무시(클라이언트 없음)
    assert "React로 대시보드를 구현" in content


def test_gather_all_content_non_string_repourl_skips_without_crash():
    # 계약 위반(repoUrl이 리스트) → unhashable로 죽지 않고 스킵(C-3)
    payload = {"narrative": {"strength": "강점"}, "experiences": [{"repoUrl": ["x"]}, {"repoUrl": None}]}
    gh = FakeGitHub({})
    content = _run(_gather_all_content(payload, gh))
    assert "강점" in content and gh.calls == []  # 비문자열은 fetch도 안 부름


# ── G-4: 업로드 문서(fileKey)가 같은 analyzer로 흘러가는지 ──────────────────


class FakeDoc:
    def __init__(self, mapping):
        self._mapping = mapping
        self.calls = []

    async def fetch_and_parse(self, file_key):
        self.calls.append(file_key)
        return self._mapping.get(file_key, "")


def test_gather_all_content_appends_document_and_dedups():
    payload = {
        "narrative": {"strength": "강점"},
        "experiences": [{"fileKey": "f1"}, {"fileKey": "f1"}, {"fileKey": "f2"}],
    }
    ds = FakeDoc({"f1": "[업로드 문서] PDF 근거", "f2": ""})
    content = _run(_gather_all_content(payload, None, ds))
    assert "PDF 근거" in content and ds.calls == ["f1", "f2"]  # f1 dedup, f2 빈 결과→빠짐


# ── H-1: 층2 guidance 쓰기가 competency 쓰기 뒤·발행 전(D-5) ──────────────


def test_guidance_write_between_competency_and_publish():
    log = []
    templates = {"react": {"none": "n", "aware": "a", "experienced": "e", "proficient": "p"}}
    repo = FakeRepo(SKILLS, log, templates=templates)
    _run(handle_roadmap_generation(PAYLOAD, FakeProvider(GOOD_RESP), FakePublisher(log), repo))
    comp_i = next(i for i, e in enumerate(log) if e[0] == "write")
    guid_i = next(i for i, e in enumerate(log) if e[0] == "write_guid")
    pub_i = next(i for i, e in enumerate(log) if e == ("publish", COMPETENCY_EXTRACTED))
    assert comp_i < guid_i < pub_i  # user_competency → user_quest_guidance → 발행


def test_gather_all_content_caps_experiences(monkeypatch):
    # 🔴 파일 다수 → Vision 비용 폭발 방지. MAX_EXPERIENCES개만 처리(리뷰 medium 수정)
    from app.config.settings import settings

    monkeypatch.setattr(settings, "MAX_EXPERIENCES", 2)
    payload = {"experiences": [{"fileKey": f"f{i}"} for i in range(10)]}
    ds = FakeDoc({f"f{i}": f"doc{i}" for i in range(10)})
    _run(_gather_all_content(payload, None, ds))
    assert ds.calls == ["f0", "f1"]  # 처음 2개만
