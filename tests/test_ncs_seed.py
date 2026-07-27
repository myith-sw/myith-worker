"""시드 무결성 + F-4 규칙 테스트. DB 없이 순수 함수만 검증한다."""

import pytest

from app.ncs.certification_loader import dedupe_certifications
from app.ncs.records import NcsCertRecord, SkillNcsMapRecord
from app.ncs.skill_map_loader import load_seed, validate_primary_uniqueness
from app.ncs.source import SeedNcsSource


def test_seed_parses():
    src = SeedNcsSource()
    units = src.fetch_units()
    certs = src.fetch_certifications()
    maps = load_seed()
    assert len(units) > 0
    # 확정 W2 D-3 대체(A안): 자격 실데이터를 확보해 시드로 넣는다. certification_loader의
    # API 커서 경로는 월 1회 갱신용으로 유지한다. 로더가 (능력단위,자격) 중복을 결정론적으로 접는다.
    assert len(certs) > 0
    assert len(maps) > 0


def test_unit_levels_in_range():
    for u in SeedNcsSource().fetch_units():
        assert 1 <= u.level <= 8, f"{u.code} level {u.level} 범위 밖 (I-2)"


def test_referential_integrity():
    unit_codes = {u.code for u in SeedNcsSource().fetch_units()}
    for c in SeedNcsSource().fetch_certifications():
        assert c.ncs_unit_code in unit_codes, f"cert가 없는 능력단위 참조: {c.ncs_unit_code}"
    for m in load_seed():
        assert m.ncs_unit_code in unit_codes, f"map이 없는 능력단위 참조: {m.ncs_unit_code}"


def test_seed_satisfies_primary_uniqueness():
    # 실제 시드가 F-4를 만족해야 한다.
    validate_primary_uniqueness(load_seed())


def test_primary_uniqueness_rejects_two_primaries():
    bad = [
        SkillNcsMapRecord("java", "u1", True),
        SkillNcsMapRecord("java", "u2", True),  # 두 번째 primary → 위반
    ]
    with pytest.raises(ValueError):
        validate_primary_uniqueness(bad)


def test_primary_uniqueness_rejects_zero_primary():
    bad = [SkillNcsMapRecord("java", "u1", False)]  # primary 없음 → 위반
    with pytest.raises(ValueError):
        validate_primary_uniqueness(bad)


def test_primary_uniqueness_allows_secondary_mappings():
    # primary 하나 + 비-primary 여러 개는 허용.
    ok = [
        SkillNcsMapRecord("docker", "u1", True),
        SkillNcsMapRecord("docker", "u2", False),
    ]
    validate_primary_uniqueness(ok)  # 예외 없어야 함


# ── 자격 중복 접기 (확정 W2 D-3 대체, A안) ────────────────────────────────


def test_dedupe_certifications_is_order_independent():
    """행 순서를 뒤집어도 결과가 같아야 멱등이다. 같은 (능력단위,자격)이 표준버전만
    다르게 여러 행 오는데, on_conflict가 파일 순서상 마지막 값을 남기면 정렬만 바뀌어도
    unit_type이 필수↔선택으로 흔들린다. 그래서 적재 전에 결정론적으로 접는다."""
    certs = SeedNcsSource().fetch_certifications()
    forward = dedupe_certifications(certs)
    reverse = dedupe_certifications(list(reversed(certs)))
    assert forward == reverse
    assert len(forward) < len(certs)  # 실제로 접혔다 (600 → 521 규모)


def test_dedupe_certifications_prefers_mandatory():
    """같은 (능력단위,자격)에 필수·선택이 섞이면 필수가 남는다 — 순서와 무관하게."""
    recs = [
        NcsCertRecord("u1", "c1", "자격A", "선택"),
        NcsCertRecord("u1", "c1", "자격A", "필수"),
    ]
    assert dedupe_certifications(recs)[0].unit_type == "필수"
    assert dedupe_certifications(list(reversed(recs)))[0].unit_type == "필수"
