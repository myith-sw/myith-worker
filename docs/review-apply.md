# 화면 텍스트 검수 재입력 (review_apply)

교수가 데모에서 **실제로 읽는 텍스트** 두 가지 — 직무 tagline(F-3 목록·F-7 상세)과 퀘스트
추천 자격(F-8) — 을 CSV로 검수한 뒤 반영하는 흐름이다. **원본 시드 JSON은 절대 수정하지 않는다**
(Part 2와 같은 원칙). 오버라이드 파일에만 쓰고, 비우면 원문으로 원복된다.

## 흐름

```
1. 덤프    scripts/gen_review_csvs.py → ~/Downloads/myith_ncs_review/
             review_taglines.csv · review_job_certs.csv
2. 수정    사람이 tagline_new 채우고, 이질 자격 행을 action=HIDE로 바꾼다
3. 재입력  python -m app.seed.review_apply --taglines <csv> --certs <csv> [--dry-run]
             → app/data/overrides/{tagline_overrides.json, cert_hidden.json}
4. 적재    python -m app.seed.load_all  (또는 개별 로더)  → 화면에 반영
```

## CSV 규칙

**review_taglines.csv** — `tagline_new`가 **비어 있으면 그 행은 건드리지 않는다**(현재 값 유지).
채운 행만 반영된다. 정렬: category_name → job_code.

**review_job_certs.csv** — 화면에 뜨는 순서대로 정렬(백엔드 먼저 → level → order_in_level →
cert_name). `action` 기본 `KEEP`, 노출에서 빼려면 **`HIDE`**. `suspect=TRUE`(직무 계열과 무관한
키워드 자동 판정) 행은 **맨 위에 모아** 둔다 — 눈으로 최종 판정한다. HIDE는 **행 삭제가 아니라
노출 제외**다.

## 재입력 명령

```bash
# 먼저 무엇이 몇 건 바뀌는지 확인 (파일 미수정)
python -m app.seed.review_apply --taglines review_taglines.csv --certs review_job_certs.csv --dry-run

# 실제 반영
python -m app.seed.review_apply --taglines review_taglines.csv --certs review_job_certs.csv
python -m app.seed.load_all       # 반영을 화면(DB)에 적재
```

## 되돌리기

오버라이드는 원본을 덮지 않으므로 **비우기만 하면 원복**된다.

```bash
# 방법 1) 명령으로 비우기
python -m app.seed.review_apply --revert
python -m app.seed.load_all       # 원문 tagline / 전체 자격으로 재적재

# 방법 2) 파일을 직접 원상복구 (git)
git checkout app/data/overrides/tagline_overrides.json app/data/overrides/cert_hidden.json
```

`tagline_overrides.json = {}`, `cert_hidden.json = []`가 "오버라이드 없음"(원문 그대로)이다.
이 두 파일은 저장소에 빈 상태로 커밋돼 있다 — 검수 결과를 커밋할지는 검수 후 판단한다.
