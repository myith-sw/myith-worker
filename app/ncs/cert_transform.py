"""자격명 정규화 (Part 2, I-3 코드형 이름).

시드 `ncs_certifications.json`의 cert_name은 `SW개발_L5_25V2`처럼 코드형이다. 화면 '추천 자격'에
그대로 노출하면 읽히지 않는다. **원본 JSON은 수정하지 않고**(무수정) 로더 적재 시점에 표시명만
`SW개발 (과정평가형 L5)`로 바꾼다. cert_code는 보존한다.

두 단계다:
  1. relabel   — 코드형 이름의 버전 접미어를 떼고 `{과정} ({라벨} L{n})`로 표시명 생성.
  2. collapse  — relabel 후 같은 (능력단위, 표시명)이 버전만 달리 여러 개면(예: _20V2·_22V2·_25V3)
                 화면에 같은 이름이 중복되므로 **최신 버전 하나만** 남긴다. YYVn(연도+판)이
                 verX.Y보다 최신(2026-07-29 승인 규칙). 접은 행은 로그로 남긴다.

순수 함수만 둔다(테스트 가능). 로더가 이 결과를 그대로 적재한다.
"""

from __future__ import annotations

import logging
import re
from dataclasses import replace

from app.ncs.records import NcsCertRecord

logger = logging.getLogger("myith.ncs.cert_transform")

MANDATORY_UNIT_TYPE = "필수"

# `{과정}_L{레벨}_{버전}` — 버전은 YYVn(25V2) 또는 verX.Y(ver3.0).
_CODE_NAME = re.compile(r"^(?P<base>.+)_L(?P<level>\d+)_(?P<ver>.+)$")
_YYVN = re.compile(r"^(?P<yy>\d{2})[Vv](?P<n>\d+)$")  # 25V2 → 연도25, 판2
_VERXY = re.compile(r"^ver(?P<x>\d+)\.(?P<y>\d+)$", re.IGNORECASE)  # ver3.0


def parse_code_name(cert_name: str) -> tuple[str, int, str] | None:
    """`SW개발_L5_25V2` → (base='SW개발', level=5, ver='25V2'). 코드형이 아니면 None."""
    m = _CODE_NAME.match(cert_name)
    if not m:
        return None
    return m.group("base"), int(m.group("level")), m.group("ver")


def version_rank(ver: str) -> tuple[int, int, int]:
    """버전 최신도 순위. 클수록 최신. YYVn이 verX.Y보다 항상 우선(선두 1 vs 0).

    YYVn  → (1, 연도, 판)   예: 25V3 → (1, 25, 3)
    verX.Y → (0, X, Y)      예: ver3.0 → (0, 3, 0)
    알 수 없는 형식 → (-1, 0, 0)  (가장 낮음)
    """
    m = _YYVN.match(ver)
    if m:
        return (1, int(m.group("yy")), int(m.group("n")))
    m = _VERXY.match(ver)
    if m:
        return (0, int(m.group("x")), int(m.group("y")))
    return (-1, 0, 0)


def display_name(cert_name: str, label: str) -> str:
    """코드형이면 `{과정} ({라벨} L{n})`, 아니면 원문 그대로."""
    parsed = parse_code_name(cert_name)
    if parsed is None:
        return cert_name
    base, level, _ver = parsed
    return f"{base} ({label} L{level})"


def _rep_better(cur: NcsCertRecord, cand: NcsCertRecord) -> bool:
    """cand가 대표(collapse 후 남길 행)로 cur보다 나은가.

    1순위: 최신 버전(version_rank). 2순위(동률): '필수'가 '선택'을 이긴다(더 강한 신호).
    코드형이 아닌 이름은 버전 순위가 (-1,0,0)이라 동률이면 필수 우선만 적용된다.
    """
    cur_v = version_rank(parse_code_name(cur.cert_name)[2]) if parse_code_name(cur.cert_name) else (-1, 0, 0)
    cand_v = version_rank(parse_code_name(cand.cert_name)[2]) if parse_code_name(cand.cert_name) else (-1, 0, 0)
    if cand_v != cur_v:
        return cand_v > cur_v
    return cur.unit_type != MANDATORY_UNIT_TYPE and cand.unit_type == MANDATORY_UNIT_TYPE


def transform_certifications(
    records: list[NcsCertRecord], label: str
) -> list[NcsCertRecord]:
    """relabel + (능력단위, 표시명) 단위 버전 collapse. 결정론적으로 정렬해 반환.

    - cert_name을 표시명으로 교체하고 cert_code는 보존한다.
    - 같은 (능력단위, 표시명) 버전 중복은 최신 하나만 남긴다(_rep_better).
    - 출력은 (능력단위, 표시명, cert_code)로 정렬 → 입력 순서와 무관하게 항상 같은 리스트(멱등).
    """
    best: dict[tuple[str, str], NcsCertRecord] = {}
    for r in records:
        key = (r.ncs_unit_code, display_name(r.cert_name, label))
        cur = best.get(key)
        if cur is None or _rep_better(cur, r):
            best[key] = r
    collapsed = len(records) - len(best)
    if collapsed:
        logger.info(
            "자격명 버전 중복 %d행 접음 (YYVn 우선): %d → %d행",
            collapsed,
            len(records),
            len(best),
        )
    out = [
        replace(rec, cert_name=name)
        for (unit, name), rec in best.items()
    ]
    out.sort(key=lambda r: (r.ncs_unit_code, r.cert_name, r.cert_code))
    return out


def apply_hidden(
    records: list[NcsCertRecord], hidden: set[tuple[str, str]]
) -> list[NcsCertRecord]:
    """검수(review_apply)에서 HIDE 처리된 (능력단위, cert_code) 행을 적재 대상에서 제외한다.

    원본 JSON은 건드리지 않는다 — 노출 제외일 뿐 삭제가 아니다. hidden이 비면 무영향.
    """
    if not hidden:
        return records
    kept = [r for r in records if (r.ncs_unit_code, r.cert_code) not in hidden]
    dropped = len(records) - len(kept)
    if dropped:
        logger.info("검수 HIDE %d행 노출 제외 (원본 무수정)", dropped)
    return kept
