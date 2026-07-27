# NCS 시드

`ncs_units.json`의 능력단위 코드·명칭·수준은 **실데이터**다 (확정 W2 A-3).
출처: 한국산업인력공단 NCS 기준정보 API(`/NCS005`)를 실호출해 추출(개정차수 29, 현행).
코드 형식은 `숫자10자리_YYvN`. `is_verified = true` — 코드·능력단위명·수준이 공식 분류표 기준이다.

## 현재 시드 (전부 실데이터)

- **능력단위 265건** — 여러 세분류에 걸침. 대표: `20010202` 응용SW엔지니어링(27건),
  `20010206` 보안엔지니어링, `02010301` 마케팅전략기획, `02020201` 인사, 그 외 IT·경영·금융·디자인·기계.
- **`description` 265/265 채워짐** — `/NCS005`의 능력단위 정의(`COMPE_UNIT_DEF`). `/NCS006` 보강 불필요.
- **`skill_ncs_map.json` 112행** — `validate_primary_uniqueness()` 통과(스킬당 primary 정확히 하나, F-4).
- **`ncs_certifications.json` 600행** — `/getNcsClCdJmList` 실호출 결과. **확정 W2 D-3(“시드로 안 넣고
  API로만”)을 대체한다** — 그 시점엔 실데이터가 없어 비웠지만 이제 확보했다. 로더가 `(능력단위,자격)`
  중복(표준버전 차이)을 결정론적으로 접어 DB **521행**으로 적재한다(`필수` 우선, `certification_loader`).
  `certification_loader`·`ncs_load_cursor`(API 커서, 1,000건/일)는 **월 1회 갱신용으로 유지** →
  “초기=시드, 갱신=API”.

## job / job_profile (`app/seed/data/`)

- `job.json` 10직무. **`available`은 DB에 저장하지 않는다** — Core가 `job_profile` 존재 여부로
  파생한다(`JobQueryService`, `profile.isPresent()`). 파일의 `available:true`는 의도 표기일 뿐이다.
  `job` 테이블 컬럼은 `job_code·job_name·category_code·category_name·tagline·ncs_detail_code`.
- `job_profile.json` 10직무 × **6축**. 최상위 키는 camelCase(`jobCode`,`questTemplates`,`activityQuests`,
  최상위 `ncsDetailCode`는 로더가 무시 — `job.ncs_detail_code`가 정본), 중첩 JSONB 내용도 camelCase
  (Core 계약, PART E). 로더가 최상위만 snake 컬럼으로 매핑한다. `d`·`level`·`axes`는 공식 산출값이니
  손으로 고치지 않는다.

## 실코드/설명 확장 방법

- **직무 트리 전체** : `/NCS001`~`/NCS004` 순회로 분류 트리 적재(향후 `taxonomy_loader`).
- **능력단위 추가** : `standard_loader`에 세분류 코드를 넘겨 `/NCS005`로 받는다. 시드가 진실의
  원천이고, API 응답은 우리 스키마(`NcsUnitRecord`)에 맞춘다.
- **자격 갱신** : `certification_loader`가 `/getNcsClCdJmList`를 능력단위별 호출(커서 재개).
