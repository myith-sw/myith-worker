"""화면 텍스트 검수 재입력 (Part 신규, 최우선).

교수가 CSV로 검수한 화면 텍스트를 오버라이드 파일에 반영한다. 흐름:

  1. (덤프)  scripts로 review_taglines.csv · review_job_certs.csv 생성 → 사람이 수정
  2. (재입력) 이 스크립트가 수정본을 읽어 app/data/overrides/*.json 에 반영
  3. (적재)  load_all(또는 개별 로더)이 오버라이드를 읽어 tagline 덮어쓰기 / cert 노출 제외

**원본 시드 JSON은 절대 수정하지 않는다**(Part 2와 같은 원칙). HIDE는 행 삭제가 아니라 노출 제외다.

사용:
  python -m app.seed.review_apply --taglines review_taglines.csv --certs review_job_certs.csv --dry-run
  python -m app.seed.review_apply --taglines review_taglines.csv --certs review_job_certs.csv
  python -m app.seed.review_apply --revert            # 오버라이드를 비워 원문으로 원복

--dry-run: 무엇이 몇 건 바뀌는지만 출력하고 파일은 건드리지 않는다(기본에 가깝게 안전).
tagline_new가 비어 있으면 그 행은 건드리지 않는다. action이 HIDE인 행만 노출 제외 대상이다.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from app.seed.overrides import CERT_HIDDEN_FILE, OVERRIDES_DIR, TAGLINE_FILE

HIDE = "HIDE"


def read_taglines(path: Path) -> dict[str, str]:
    """job_code → tagline_new (비어있지 않은 행만). BOM 허용(utf-8-sig)."""
    out: dict[str, str] = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            code = (row.get("job_code") or "").strip()
            new = (row.get("tagline_new") or "").strip()
            if code and new:
                out[code] = new
    return out


def read_cert_hidden(path: Path) -> list[list[str]]:
    """action==HIDE인 (ncs_unit_code, cert_code) 목록. 중복 제거, 정렬(결정론)."""
    seen: set[tuple[str, str]] = set()
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if (row.get("action") or "").strip().upper() != HIDE:
                continue
            unit = (row.get("ncs_unit_code") or "").strip()
            cert = (row.get("cert_code") or "").strip()
            if unit and cert:
                seen.add((unit, cert))
    return [list(k) for k in sorted(seen)]


def _write(path: Path, data: object) -> None:
    OVERRIDES_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="화면 텍스트 검수 재입력")
    ap.add_argument("--taglines", type=Path, help="수정된 review_taglines.csv")
    ap.add_argument("--certs", type=Path, help="수정된 review_job_certs.csv")
    ap.add_argument("--dry-run", action="store_true", help="변경 요약만 출력, 파일 미수정")
    ap.add_argument("--revert", action="store_true", help="오버라이드를 비워 원문으로 원복")
    args = ap.parse_args(argv)

    if args.revert:
        if args.dry_run:
            print("[dry-run] 오버라이드를 비웠을 것 (tagline_overrides={}, cert_hidden=[])")
            return 0
        _write(TAGLINE_FILE, {})
        _write(CERT_HIDDEN_FILE, [])
        print("원복 완료: tagline_overrides={}, cert_hidden=[]  → 다음 적재부터 원문 시드 사용")
        return 0

    if not args.taglines and not args.certs:
        ap.error("--taglines / --certs / --revert 중 하나는 필요하다")

    taglines = read_taglines(args.taglines) if args.taglines else None
    hidden = read_cert_hidden(args.certs) if args.certs else None

    # 항상 변경 요약을 먼저 출력한다.
    if taglines is not None:
        print(f"tagline 반영 대상: {len(taglines)}건 (tagline_new 채워진 행)")
        for code, new in sorted(taglines.items()):
            print(f"  {code}: {new}")
    if hidden is not None:
        print(f"cert 노출 제외(HIDE): {len(hidden)}건")
        for unit, cert in hidden:
            print(f"  {unit} / {cert}")

    if args.dry_run:
        print("[dry-run] 파일을 수정하지 않았다. 반영하려면 --dry-run 없이 다시 실행.")
        return 0

    if taglines is not None:
        _write(TAGLINE_FILE, taglines)
        print(f"→ {TAGLINE_FILE.name} 기록")
    if hidden is not None:
        _write(CERT_HIDDEN_FILE, hidden)
        print(f"→ {CERT_HIDDEN_FILE.name} 기록")
    print("반영 완료. load_all(또는 개별 로더) 재실행 시 화면에 반영된다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
