# NCS 시드

`ncs_units.json`의 능력단위 코드·명칭·수준은 **실데이터**다 (확정 W2 A-3).
출처: 한국산업인력공단 NCS 세분류 **`20010202` 응용SW엔지니어링**
(대분류 `20` 정보통신 › 중분류 `2001` 정보기술 › 소분류 `200102` 정보기술개발).
코드 형식은 `숫자10자리_YYvN`. `is_verified = true` — 코드·능력단위명·수준 3개 필드가 공식 분류표 기준이다.

## 진행 체크리스트 (확정 W2 A-3 / D-3, 확장직무설계)

- [x] 능력단위 코드·명칭·수준 : 실데이터 27건 반영 (`20010202` 응용SW엔지니어링). `is_verified=true`.
- [x] `skill_ncs_map` : 51행 반영. `validate_primary_uniqueness()` 통과(스킬당 primary 정확히 하나).
- [ ] `description` : 임시 작성값. `/NCS006` 능력단위요소로 나중에 덮어쓴다.
- [x] `ncs_certifications.json` : 비웠다(`[]`). 종목코드는 추측 불가 — `/getNcsClCdJmList`로만 적재.
      `ncs_load_cursor`로 중단·재개(1,000건/일 쿼터 대비).
- [ ] 정보보호 세분류 : 추가 확보 대기. 확보 시 `security`·`spring-security` 스킬을 그때 매핑
      (응용SW엔지니어링엔 보안 능력단위가 없어 지금은 넣지 않는다).
- [ ] 마케팅 세분류 : `digital-marketer` 직무용. 추가 확보 대기.

## 실코드/설명 확장 방법

- **직무 트리 전체** : `/NCS001`~`/NCS004`를 순회해 분류 트리를 적재(향후 `taxonomy_loader`).
- **능력단위 추가** : `standard_loader`에 세분류 코드를 넘겨 `/NCS005`로 받는다. 데이터는 시드가
  진실의 원천이고, API 응답 매핑은 우리 스키마(`NcsUnitRecord`)에 맞춘다.
- **자격 종목** : `certification_loader`가 `/getNcsClCdJmList`를 능력단위별로 호출(커서 재개).
