"""화면 텍스트 검수 CSV 덤프 (docs/review-apply.md 1단계).

교수가 데모에서 실제로 읽는 텍스트를 사람이 검수할 CSV로 뽑는다. **읽기 전용** — DB도 원본 시드도
건드리지 않는다. 결과 CSV는 저장소에 커밋하지 않는다(검수 중 산출물). 시드가 바뀌면 다시 돌린다.

    PYTHONPATH=. python scripts/gen_review_csvs.py [--out DIR]

출력(기본 ~/Downloads/myith_ncs_review/):
  review_taglines.csv   직무 한마디 소개 (tagline_new 빈칸 — 사람이 채운다)
  review_job_certs.csv  퀘스트 추천 자격 (화면 순서, suspect 자동판정, action=KEEP)
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from app.config.settings import settings
from app.ncs.cert_transform import transform_certifications
from app.ncs.records import NcsCertRecord

REPO = Path(__file__).resolve().parents[1]

# suspect는 "해당 직무 계열과 무관한" 키워드만 잡는다(job-relative). 직무 자기 계열 키워드는 제외한다
# — 제조 직무엔 기계·가공이 정상이라 이물이 아니다. 다른 계열(자동차·전기 등)이 섞이면 그건 잡힌다.
# IT/경영/디자인 직무엔 이 목록 전체가 이물이다. 완벽할 필요 없다 — 사람이 눈으로 최종 판정한다.
OWN_FIELD_BY_CATEGORY = {
    "생산-제조": {"기계", "금형", "용접", "설비", "가공", "주조", "판금", "배관", "도장", "측량", "제철", "화학"},
}


def _suspect(keywords, own, cert_name: str, unit_name: str) -> bool:
    hay = f"{cert_name} {unit_name}"
    return any(k in hay for k in keywords if k not in own)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="화면 텍스트 검수 CSV 덤프")
    ap.add_argument("--out", type=Path, default=Path.home() / "Downloads" / "myith_ncs_review")
    args = ap.parse_args(argv)
    out = args.out
    out.mkdir(parents=True, exist_ok=True)

    jobs = json.loads((REPO / "app/seed/data/job.json").read_text(encoding="utf-8"))
    profiles = json.loads((REPO / "app/seed/data/job_profile.json").read_text(encoding="utf-8"))
    raw_certs = json.loads((REPO / "app/data/ncs_seed/ncs_certifications.json").read_text(encoding="utf-8"))

    # 화면과 동일한 표시명으로 변환한 뒤 능력단위별로 모은다.
    certs = transform_certifications(
        [NcsCertRecord(**r) for r in raw_certs], settings.CERT_ASSESSMENT_LABEL
    )
    by_unit: dict[str, list[NcsCertRecord]] = defaultdict(list)
    for c in certs:
        by_unit[c.ncs_unit_code].append(c)
    job_name = {j["job_code"]: j["job_name"] for j in jobs}
    cat_of = {j["job_code"]: (j.get("category_name") or "") for j in jobs}

    # ── review_taglines.csv (category → job_code) ──
    tag_rows = sorted(jobs, key=lambda j: (j.get("category_name") or "", j["job_code"]))
    with (out / "review_taglines.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["job_code", "job_name", "category_name", "tagline_current", "char_len", "tagline_new"])
        for j in tag_rows:
            t = j.get("tagline") or ""
            w.writerow([j["job_code"], j["job_name"], j.get("category_name") or "", t, len(t), ""])
    print(f"review_taglines.csv: {len(tag_rows)}행")

    # ── review_job_certs.csv (백엔드 먼저 → level → order_in_level → cert_name) ──
    kw = settings.CERT_SUSPECT_KEYWORDS
    job_order = {"backend": 0}
    rows: list[dict] = []
    for prof in profiles:
        jc = prof["jobCode"]
        axis = {a["axisCode"]: a for a in prof["axes"]}
        qt = {q["skillCode"]: q for q in prof["questTemplates"]}
        order_in_level: dict[str, int] = {}
        for lv in prof["levels"]:
            for i, sc in enumerate(lv["skillCodes"]):
                order_in_level[sc] = i
        own = OWN_FIELD_BY_CATEGORY.get(cat_of.get(jc, ""), set())
        for sk in prof["skills"]:
            q = qt.get(sk["skillCode"])
            if not q:
                continue
            ax = axis.get(sk["axisCode"], {})
            unit_code = q.get("ncsUnitCode") or ax.get("ncsUnitCode", "")
            unit_name = ax.get("ncsUnitName", "")
            skill_certs = by_unit.get(unit_code, [])
            for c in skill_certs:
                rows.append({
                    "job_code": jc, "job_name": job_name.get(jc, jc), "level": sk["level"],
                    "skill_code": sk["skillCode"], "skill_name": sk["skillName"],
                    "quest_title": q["title"], "axis_name": ax.get("axisName", ""),
                    "ncs_unit_code": unit_code, "ncs_unit_name": unit_name,
                    "cert_code": c.cert_code, "cert_name": c.cert_name,
                    "unit_type": c.unit_type or "", "cert_count_for_skill": len(skill_certs),
                    "suspect": "TRUE" if _suspect(kw, own, c.cert_name, unit_name) else "FALSE",
                    "action": "KEEP", "_ord": order_in_level.get(sk["skillCode"], 999),
                })

    rows.sort(key=lambda r: (
        0 if r["suspect"] == "TRUE" else 1,
        job_order.get(r["job_code"], 1), r["job_code"],
        r["level"], r["_ord"], r["cert_name"],
    ))
    cols = ["job_code", "job_name", "level", "skill_code", "skill_name", "quest_title",
            "axis_name", "ncs_unit_code", "ncs_unit_name", "cert_code", "cert_name",
            "unit_type", "cert_count_for_skill", "suspect", "action"]
    with (out / "review_job_certs.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    n_susp = sum(1 for r in rows if r["suspect"] == "TRUE")
    print(f"review_job_certs.csv: {len(rows)}행 (suspect TRUE {n_susp}행 상단)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
