"""guidance_tier 경계값 검증 (확정 W2 B-1). 4구간, 순수 함수."""

import pytest

from app.pipeline.guidance import GUIDANCE_TIERS, guidance_tier


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
