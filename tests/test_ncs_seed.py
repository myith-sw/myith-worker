"""시드 무결성 + F-4 규칙 테스트. DB 없이 순수 함수만 검증한다."""

import pytest

from app.ncs.records import SkillNcsMapRecord
from app.ncs.skill_map_loader import load_seed, validate_primary_uniqueness
from app.ncs.source import SeedNcsSource


def test_seed_parses():
    src = SeedNcsSource()
    units = src.fetch_units()
    certs = src.fetch_certifications()
    maps = load_seed()
    assert 5 <= len(units) <= 8  # 백엔드 직무 기준 5~8개 (제약)
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
