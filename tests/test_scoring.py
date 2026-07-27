"""난이도 S 폴백 + D 공식 검증 (확정 W2 A-4, F-5). 순수 함수."""

from app.config.settings import settings
from app.datasource.base import Posting
from app.pipeline.scoring import compute_d, compute_n, compute_s, job_entry_signal


def _posting(entry):
    return Posting(posting_id="x", skill_tags=[], requirement_text="", accepts_entry_level=entry)


def test_entry_signal_present_when_any_not_none():
    postings = [_posting(None), _posting(True), _posting(None)]
    assert job_entry_signal(postings, "backend") is True


def test_entry_signal_absent_when_all_none():
    postings = [_posting(None), _posting(None)]
    assert job_entry_signal(postings, "backend") is False


def test_compute_s_formula_when_signal_present():
    # 10건 중 4건 신입수용 → S = 1 - 4/10 = 0.6
    assert abs(compute_s(10, 4, True) - 0.6) < 1e-9


def test_compute_s_falls_back_to_neutral_when_no_signal():
    # 신호 없음 → 0이 아니라 중립값(0.5)
    assert compute_s(10, 0, False) == settings.SCORING_DEFAULT_S
    assert settings.SCORING_DEFAULT_S == 0.5


def test_compute_s_falls_back_when_total_zero():
    assert compute_s(0, 0, True) == settings.SCORING_DEFAULT_S


def test_compute_s_never_zero_from_absent_signal():
    # 전부 None인데 S=0이면 "전 직무 신입 100% 수용"이 되어 D가 왜곡된다. 방어.
    assert compute_s(5, 0, False) != 0.0


def test_compute_n_normalization():
    assert compute_n(1) == 0.0
    assert abs(compute_n(8) - 1.0) < 1e-9


def test_compute_d_matches_confirmed_formula():
    s, p, n = 0.6, 0.5, compute_n(4)
    expected = 0.45 * s + 0.30 * (1 - p) + 0.25 * n
    assert abs(compute_d(s, p, n) - expected) < 1e-9
