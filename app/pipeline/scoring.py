"""난이도 산출 (F-5). 순수 함수 — 단위 테스트로 공식을 지킨다.

D = SCORING_WEIGHT_S·S + SCORING_WEIGHT_P·(1−P) + SCORING_WEIGHT_N·N
  S = 1 − (entry_level_count / total_count)   경력장벽
  P = total_count / 직무 내 최대 total_count   시장 보편성
  N = (ncs_unit.level − 1) / 7                 NCS 수준 정규화

S 폴백 (확정 W2 A-4): 표본에 신입수용 신호(accepts_entry_level)가 전무하면 S를
SCORING_DEFAULT_S(0.5=중립)로 고정한다. 0으로 두면 "전 직무가 신입 100% 수용"이
되어 D가 통째로 왜곡된다.
"""

import logging

from app.config.settings import settings
from app.datasource.base import Posting

logger = logging.getLogger("myith.pipeline.scoring")


def job_entry_signal(postings: list[Posting], job_code: str) -> bool:
    """직무 표본에 신입수용 신호가 하나라도 있으면 True. 전무하면 WARNING 로그."""
    present = any(p.accepts_entry_level is not None for p in postings)
    if not present:
        logger.warning(
            "entry-level 신호 없음. S=기본값으로 폴백 (job_code=%s)", job_code
        )
    return present


def compute_s(
    total_count: int, entry_level_count: int, entry_signal_present: bool
) -> float:
    """경력장벽 S. 신호가 없거나 표본이 비면 중립값(SCORING_DEFAULT_S)."""
    if not entry_signal_present or total_count == 0:
        return settings.SCORING_DEFAULT_S
    return 1.0 - (entry_level_count / total_count)


def compute_n(ncs_level: int) -> float:
    """NCS 수준(1~8) → 0~1 정규화."""
    return (ncs_level - 1) / 7


def compute_d(s: float, p: float, n: float) -> float:
    """확정 난이도 공식 (F-5). 가중치는 설정값, 임의로 바꾸지 않는다."""
    return (
        settings.SCORING_WEIGHT_S * s
        + settings.SCORING_WEIGHT_P * (1 - p)
        + settings.SCORING_WEIGHT_N * n
    )
