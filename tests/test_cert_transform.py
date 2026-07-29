"""자격명 정규화 (Part 2). relabel + 버전 collapse(YYVn 우선) + HIDE 노출제외. 순수 함수."""

from app.ncs.cert_transform import (
    apply_hidden,
    display_name,
    parse_code_name,
    transform_certifications,
    version_rank,
)
from app.ncs.records import NcsCertRecord

LABEL = "과정평가형"


def _c(unit, code, name, ut="필수"):
    return NcsCertRecord(ncs_unit_code=unit, cert_code=code, cert_name=name, unit_type=ut)


# ── parse / display ─────────────────────────────────────────────────────


def test_parse_code_name():
    assert parse_code_name("SW개발_L5_25V2") == ("SW개발", 5, "25V2")
    assert parse_code_name("CNC밀링가공_L3_ver2.0") == ("CNC밀링가공", 3, "ver2.0")
    assert parse_code_name("정보처리기사") is None  # 코드형 아님


def test_display_name_relabels_code_style_only():
    assert display_name("SW개발_L5_25V2", LABEL) == "SW개발 (과정평가형 L5)"
    assert display_name("CNC밀링가공_L3_ver2.0", LABEL) == "CNC밀링가공 (과정평가형 L3)"
    assert display_name("정보처리기사", LABEL) == "정보처리기사"  # 원문 유지


# ── version_rank: YYVn > verX.Y, 그 안에서 수치 비교 ─────────────────────


def test_version_rank_yyvn_beats_verxy():
    assert version_rank("20V1") > version_rank("ver3.0")  # 연도형이 항상 위
    assert version_rank("25V3") > version_rank("22V2")  # 최신 연도
    assert version_rank("25V3") > version_rank("25V2")  # 같은 연도, 높은 판
    assert version_rank("ver3.0") > version_rank("ver2.0")
    assert version_rank("garbage") == (-1, 0, 0)  # 미지 형식 최하


# ── collapse: 같은 (unit, 표시명) 버전 중복 → 최신 하나 ───────────────────


def test_collapse_keeps_latest_version_per_unit():
    recs = [
        _c("U1", "A20", "SW개발_L3_20V2"),
        _c("U1", "A22", "SW개발_L3_22V2"),
        _c("U1", "A25", "SW개발_L3_25V3"),
    ]
    out = transform_certifications(recs, LABEL)
    assert len(out) == 1
    assert out[0].cert_name == "SW개발 (과정평가형 L3)"
    assert out[0].cert_code == "A25"  # 25V3가 최신 → cert_code 보존


def test_collapse_yyvn_wins_over_verxy_in_mixed_group():
    recs = [
        _c("U1", "V30", "구조해석설계_L4_ver3.0"),
        _c("U1", "Y23", "구조해석설계_L4_23V2"),
        _c("U1", "Y20", "구조해석설계_L4_20V1"),
    ]
    out = transform_certifications(recs, LABEL)
    assert len(out) == 1 and out[0].cert_code == "Y23"  # 23V2 (YYVn 최신)


def test_no_collapse_across_different_units():
    recs = [
        _c("U1", "A25", "SW개발_L3_25V3"),
        _c("U2", "A20", "SW개발_L3_20V2"),  # 다른 능력단위 → 각자 유지
    ]
    out = transform_certifications(recs, LABEL)
    assert len(out) == 2
    assert {r.ncs_unit_code for r in out} == {"U1", "U2"}


def test_non_code_names_pass_through_unchanged():
    recs = [_c("U1", "C1", "정보처리기사"), _c("U1", "C2", "정보보안기사")]
    out = transform_certifications(recs, LABEL)
    assert {r.cert_name for r in out} == {"정보처리기사", "정보보안기사"}


def test_transform_is_deterministic_regardless_of_input_order():
    a = [_c("U1", "A25", "SW개발_L3_25V3"), _c("U1", "A20", "SW개발_L3_20V2")]
    b = list(reversed(a))
    assert transform_certifications(a, LABEL) == transform_certifications(b, LABEL)


def test_mandatory_wins_on_version_tie():
    # 같은 버전(동률)이면 필수가 선택을 이긴다
    recs = [
        _c("U1", "S1", "SW개발_L3_25V3", ut="선택"),
        _c("U1", "M1", "SW개발_L3_25V3", ut="필수"),
    ]
    out = transform_certifications(recs, LABEL)
    assert len(out) == 1 and out[0].unit_type == "필수"


# ── apply_hidden: 노출 제외(삭제 아님) ───────────────────────────────────


def test_apply_hidden_excludes_matching_pair():
    recs = [_c("U1", "A", "정보처리기사"), _c("U1", "B", "정보보안기사")]
    out = apply_hidden(recs, {("U1", "A")})
    assert [r.cert_code for r in out] == ["B"]


def test_apply_hidden_empty_is_noop():
    recs = [_c("U1", "A", "정보처리기사")]
    assert apply_hidden(recs, set()) == recs
