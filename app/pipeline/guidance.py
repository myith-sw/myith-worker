"""퀘스트 문구 개인화 층1 — 규칙 판정 (확정 W2 B-1, H-1).

자가진단 M값은 4개다: 0.00 / 0.33 / 0.66 / 1.00. 0.66과 1.00을 합치지 않는다 —
둘 다 ALREADY_KNOWN이지만 "이미 아는 것으로 처리했다"와 "심화 사례를 남겨라"는
다른 안내다. quest_templates[].guidance의 키가 이 4종이다.

이 판정에 LLM은 관여하지 않는다 (C-2). 층2(LLM)는 narrative가 있을 때만 선택된
문구를 다듬는다.
"""

# quest_templates[].guidance가 가져야 할 키 (순서 = M 오름차순)
GUIDANCE_TIERS: tuple[str, ...] = ("none", "aware", "experienced", "proficient")


def guidance_tier(mastery: float) -> str:
    """M값 → guidance 키.

    M < 0.33            → none          전혀 모름
    0.33 ≤ M < 0.66     → aware         들어봤다 / 조금 안다
    0.66 ≤ M < 1.0      → experienced   해본 적 있다 (ALREADY_KNOWN)
    M ≥ 1.0             → proficient    능숙하다     (ALREADY_KNOWN)
    """
    if mastery < 0.33:
        return "none"
    if mastery < 0.66:
        return "aware"
    if mastery < 1.0:
        return "experienced"
    return "proficient"
