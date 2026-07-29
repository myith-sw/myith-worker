"""검수 오버라이드 파일 읽기 (화면 텍스트 검수, review_apply의 반영 대상).

교수가 화면에 실제로 노출되는 텍스트(직무 tagline, 퀘스트 추천 자격)를 CSV로 검수한 뒤
`review_apply`가 이 두 파일에 반영한다. 로더는 적재 시 이 파일들을 읽어 덮어쓰거나 노출 제외한다.

  tagline_overrides.json : {job_code: tagline}          load_jobs가 tagline을 덮어씀
  cert_hidden.json       : [[ncs_unit_code, cert_code]]  certification_loader가 노출 제외

**원본 시드(JSON)는 수정하지 않는다** — 오버라이드일 뿐이라 파일을 비우면(또는 지우면) 원복된다.
파일이 없으면 무영향(빈 오버라이드). 되돌리는 법은 docs/review-apply.md 참조.
"""

from __future__ import annotations

import json
from pathlib import Path

OVERRIDES_DIR = Path(__file__).resolve().parent.parent / "data" / "overrides"
TAGLINE_FILE = OVERRIDES_DIR / "tagline_overrides.json"
CERT_HIDDEN_FILE = OVERRIDES_DIR / "cert_hidden.json"


def load_tagline_overrides(path: Path = TAGLINE_FILE) -> dict[str, str]:
    """{job_code: tagline}. 파일 없거나 비면 {}."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {str(k): str(v) for k, v in data.items() if str(v).strip()}


def load_cert_hidden(path: Path = CERT_HIDDEN_FILE) -> set[tuple[str, str]]:
    """{(ncs_unit_code, cert_code)}. 파일 없거나 비면 빈 집합."""
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return {(str(u), str(c)) for u, c in data}
