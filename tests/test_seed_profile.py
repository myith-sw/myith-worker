"""job·job_profile 시드 정합성 + 확정 D 공식 검증. DB 없이 순수 검증만 한다.

시드 job_profile은 데모에서 그대로 쓰인다(확정 Step 6). 축·스킬·레벨·선후관계·
문항·템플릿이 서로 어긋나면 화면이 깨지므로 여기서 강하게 묶어 검증한다.
모든 프로필(backend, frontend, ...)에 대해 동일 규칙을 강제한다.
"""

import json
import re

import pytest

from app.config.settings import settings
from app.ncs.skill_map_loader import load_seed as load_skill_seed
from app.ncs.source import SeedNcsSource
from app.pipeline.guidance import GUIDANCE_TIERS
from app.seed import SEED_DATA_DIR


def _load(name):
    with (SEED_DATA_DIR / name).open(encoding="utf-8") as f:
        return json.load(f)


# job_profile.json은 최상위 키가 camelCase다(jobCode, questTemplates, ...). 중첩 내용도 camelCase.
_PROFILES = _load("job_profile.json")
_PROFILE_CODES = [p["jobCode"] for p in _PROFILES]


def _profile(job_code):
    return next(p for p in _PROFILES if p["jobCode"] == job_code)


def _primary_map():
    return {m.skill_code: m.ncs_unit_code for m in load_skill_seed() if m.is_primary}


# ── job 마스터 ───────────────────────────────────────────────────────────


def test_jobs_parse_and_contain_backend():
    jobs = _load("job.json")
    codes = {j["job_code"] for j in jobs}
    assert "backend" in codes
    for j in jobs:
        assert j["job_name"] and j["job_code"]


def test_jobs_have_expected_ncs_detail_codes():
    # 확정 W2 C-6 + 실데이터 확장: backend·frontend는 20010202. 실데이터 교체 후엔
    # 10직무 전부 NCS 세분류에 연결된다(NULL 없음). 대표 매핑을 못 박아 회귀를 막는다.
    jobs = {j["job_code"]: j for j in _load("job.json")}
    assert jobs["backend"]["ncs_detail_code"] == "20010202"
    assert jobs["frontend"]["ncs_detail_code"] == "20010202"
    assert jobs["security"]["ncs_detail_code"] == "20010206"
    assert jobs["marketer"]["ncs_detail_code"] == "02010301"
    assert jobs["hr"]["ncs_detail_code"] == "02020201"
    for j in jobs.values():
        assert j.get("ncs_detail_code"), f"{j['job_code']} ncs_detail_code 없음"


def test_profiled_jobs_exist_in_job_master():
    job_codes = {j["job_code"] for j in _load("job.json")}
    for code in _PROFILE_CODES:
        assert code in job_codes, f"job_profile {code}에 대응하는 job 행이 없다"


# ── 프로필 정합성 (모든 프로필에 대해) ───────────────────────────────────


def test_profiles_present():
    # 확정 W2 A-2: backend 완성 + frontend 추가 = 최소 2개.
    assert "backend" in _PROFILE_CODES
    assert "frontend" in _PROFILE_CODES


@pytest.mark.parametrize("code", _PROFILE_CODES)
def test_profile_basic(code):
    p = _profile(code)
    assert p["version"] >= 1
    assert p["skills"] and p["axes"] and p["levels"]


@pytest.mark.parametrize("code", _PROFILE_CODES)
def test_skill_axis_references_valid(code):
    p = _profile(code)
    axis_codes = {a["axisCode"] for a in p["axes"]}
    for s in p["skills"]:
        assert s["axisCode"] in axis_codes, f"[{code}] {s['skillCode']} → 없는 축 {s['axisCode']}"


@pytest.mark.parametrize("code", _PROFILE_CODES)
def test_axis_ncs_unit_references_valid(code):
    p = _profile(code)
    unit_codes = {u.code for u in SeedNcsSource().fetch_units()}
    for a in p["axes"]:
        assert a["ncsUnitCode"] in unit_codes, f"[{code}] 축 {a['axisCode']} → 없는 NCS {a['ncsUnitCode']}"


@pytest.mark.parametrize("code", _PROFILE_CODES)
def test_each_skill_has_primary_mapping_matching_axis(code):
    """모든 스킬은 primary NCS 매핑을 갖고, 그 능력단위가 스킬 축의 NCS와 일치한다 (F-4)."""
    p = _profile(code)
    primary = _primary_map()
    axis_ncs = {a["axisCode"]: a["ncsUnitCode"] for a in p["axes"]}
    for s in p["skills"]:
        sc = s["skillCode"]
        assert sc in primary, f"[{code}] {sc} primary 매핑 없음"
        assert primary[sc] == axis_ncs[s["axisCode"]], (
            f"[{code}] {sc} primary NCS({primary[sc]}) != 축 NCS({axis_ncs[s['axisCode']]})"
        )


@pytest.mark.parametrize("code", _PROFILE_CODES)
def test_levels_cover_all_skills_consistently(code):
    p = _profile(code)
    skill_level = {s["skillCode"]: s["level"] for s in p["skills"]}
    from_levels = {}
    for band in p["levels"]:
        for c in band["skillCodes"]:
            from_levels[c] = band["level"]
    assert set(skill_level) == set(from_levels), f"[{code}] skills와 levels 스킬 집합 불일치"
    for c, lv in skill_level.items():
        assert from_levels[c] == lv, f"[{code}] {c} skill.level({lv}) != levels 밴드({from_levels[c]})"


@pytest.mark.parametrize("code", _PROFILE_CODES)
def test_levels_within_band_range(code):
    p = _profile(code)
    levels = [b["level"] for b in p["levels"]]
    assert settings.LEVEL_BAND_MIN <= max(levels) <= settings.LEVEL_BAND_MAX


@pytest.mark.parametrize("code", _PROFILE_CODES)
def test_prerequisites_reference_existing_and_respect_level_order(code):
    p = _profile(code)
    skill_level = {s["skillCode"]: s["level"] for s in p["skills"]}
    for edge in p["prerequisites"]:
        assert edge["from"] in skill_level, f"[{code}] 선수 {edge['from']} 없음"
        assert edge["to"] in skill_level, f"[{code}] 후행 {edge['to']} 없음"
        # 선수가 후행보다 높은 Lv이면 안 된다 (F-8 위배 검증)
        assert skill_level[edge["from"]] <= skill_level[edge["to"]], (
            f"[{code}] 선후 위배: {edge['from']}(Lv{skill_level[edge['from']]}) → "
            f"{edge['to']}(Lv{skill_level[edge['to']]})"
        )


@pytest.mark.parametrize("code", _PROFILE_CODES)
def test_questions_reference_existing_skills_and_axes(code):
    p = _profile(code)
    skill_codes = {s["skillCode"] for s in p["skills"]}
    axis_codes = {a["axisCode"] for a in p["axes"]}
    assert len(p["questions"]) <= 10  # 8개 내외 (F-9)
    for q in p["questions"]:
        assert q["skillCode"] in skill_codes
        assert q["axisCode"] in axis_codes
        assert q["text"].strip()


@pytest.mark.parametrize("code", _PROFILE_CODES)
def test_quest_templates_cover_all_skills_with_guidance(code):
    p = _profile(code)
    skill_codes = {s["skillCode"] for s in p["skills"]}
    primary = _primary_map()
    templated = {t["skillCode"] for t in p["questTemplates"]}
    assert templated == skill_codes, f"[{code}] quest_templates가 모든 스킬을 덮지 않음"
    for t in p["questTemplates"]:
        assert t["title"].strip() and t["completionCriteria"].strip()
        assert t["ncsUnitCode"] == primary[t["skillCode"]]
        g = t["guidance"]
        # 확정 W2 B-1: guidance는 4종 (none/aware/experienced/proficient)
        assert set(g) == set(GUIDANCE_TIERS), f"[{code}] {t['skillCode']} guidance 키가 4종이 아님: {set(g)}"
        for band in GUIDANCE_TIERS:
            assert g[band].strip(), f"[{code}] {t['skillCode']} guidance.{band} 비어있음"


@pytest.mark.parametrize("code", _PROFILE_CODES)
def test_activity_quests_have_no_skill_but_valid_axis(code):
    p = _profile(code)
    axis_codes = {a["axisCode"] for a in p["axes"]}
    for aq in p["activityQuests"]:
        assert "skillCode" not in aq or aq.get("skillCode") is None  # F-9: skill_code 없음
        assert aq["axisCode"] in axis_codes  # axis_code는 필수
        assert settings.LEVEL_BAND_MIN <= aq["level"] <= settings.LEVEL_BAND_MAX


@pytest.mark.parametrize("code", _PROFILE_CODES)
def test_difficulty_matches_confirmed_formula(code):
    """D = 0.45·S + 0.30·(1−P) + 0.25·N (F-5). 시드 d가 공식과 일치하는지."""
    p = _profile(code)
    for s in p["skills"]:
        expected = (
            settings.SCORING_WEIGHT_S * s["s"]
            + settings.SCORING_WEIGHT_P * (1 - s["p"])
            + settings.SCORING_WEIGHT_N * s["n"]
        )
        assert abs(expected - s["d"]) < 1e-3, (
            f"[{code}] {s['skillCode']} d={s['d']} != 공식값 {expected:.4f}"
        )


# ── NCS 실데이터 (확정 W2 A-3) ───────────────────────────────────────────


def test_seed_units_are_real_verified_codes():
    """확정 W2 A-3 + 실데이터 확장: 265건, is_verified=true, 코드 형식 검증, TBD 잔재 없음."""
    units = SeedNcsSource().fetch_units()
    assert len(units) == 265
    for u in units:
        # 코드 형식: 10자리 숫자_YYvN. 과거 가짜코드가 두 번 들어왔다 —
        # L2001010106_18v4(L 접두어=학습모듈)와 세분류가 틀린 코드. 둘 다 그럴듯해 눈으론 못 걸렀다.
        # 개수(len==265) 검사는 못 잡지만 이 정규식은 L 접두어를 즉시 잡고, 형식은 데이터가 늘어도 안 변한다.
        assert re.fullmatch(r"\d{10}_\d{2}v\d+", u.code), f"코드 형식 위반: {u.code}"
        assert not u.code.startswith("TBD-"), f"TBD 잔재: {u.code}"
        assert u.is_verified is True
    # 응용SW엔지니어링(20010202) 세분류가 부분집합으로 존재해야 한다 (backend·frontend 근거, 27건).
    assert any(u.code.startswith("20010202") for u in units)
