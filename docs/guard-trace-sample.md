# 가드 트레이스 — "LLM을 믿지 않는다"의 숫자 근거

역량 추출에서 **LLM이 낸 판정 중 가드가 몇 개를 왜 버렸는지**를 구조화 카운터로 남긴다.
`apply_guards`가 매 실행마다 이 값을 로그로 찍는다([analyzer.py](../app/competency/analyzer.py) — `guard_trace ...`).

> **발표에는 아래 §2 실측 섹션만 쓴다.** §1은 가드 로직 검증용 모의 실행이다(입력이 모의).
> 리허설에서 실 LLM을 1회 돌려 로그 한 줄을 뽑아 §2에 붙이면 그걸로 교체한다.

## 형식

```json
{
  "input_candidates": 10,        // 닫힌 집합으로 LLM에 준 스킬 수
  "llm_returned": 12,            // LLM이 판정한 스킬 수
  "dropped_out_of_set": 2,       // 목록 밖 스킬 (가드1)
  "dropped_no_evidence": 4,      // 근거 없음/원문에 실재하지 않음 (가드2)
  "dropped_low_confidence": 0,   // 신뢰도 임계 미달 (가드3)
  "dropped_schema": 0,           // 타입·범위 오류 (가드4 파싱)
  "dropped_fabrication": 0,      // competency엔 별도 사실검증 없음(STAR H-2 가드) — 형식 일관용
  "dropped_duplicate": 0,        // 같은 스킬 중복
  "accepted": 6                  // 최종 반영
}
```

## 로그 라인 포맷 (이걸 긁어온다)

`app/competency/analyzer.py`가 이 형태로 stdout에 찍는다 — `guard_trace ` 뒤에 위 JSON이 한 줄로
붙는다(`json.dumps`, 콤마·콜론 뒤 공백 있음). 로거 프리픽스(시각·레벨) 뒤에 온다:

```
2026-07-29 12:34:56,789 INFO guard_trace {"input_candidates": 10, "llm_returned": 12, "dropped_out_of_set": 2, "dropped_no_evidence": 4, "dropped_low_confidence": 0, "dropped_schema": 0, "dropped_fabrication": 0, "dropped_duplicate": 0, "accepted": 6}
```

**긁어올 것:** `guard_trace ` **다음의 `{...}` JSON 오브젝트 한 개**(프리픽스는 버려도 됨).
캡처 명령:

```bash
docker compose -f docker-compose.worker.yml logs worker 2>&1 \
  | grep "guard_trace" | tail -1
```

이 줄을 아래 §2에 그대로 붙이면 된다.

---

## §1. 모의 실행 (⚠️ 모의 입력 — 발표에 쓰지 않음)

> 백엔드 산출물 **예시 입력(모의 LLM 응답 12건)** 에 **실제 `apply_guards` 코드를 그대로 돌린
> 결과**다. 입력만 모의고 숫자는 가드 로직이 계산한 실값이다. 가드 코드가 실제로 거른다는 검증용.

| 항목 | 값 |
|---|---|
| input_candidates | 10 |
| llm_returned | **12** |
| dropped_out_of_set | 2 (kubernetes, kafka — 닫힌 목록 밖) |
| dropped_no_evidence | 4 (aws·jpa·typescript·중복spring — 근거가 원문에 실재하지 않음) |
| dropped_low_confidence | 0 |
| accepted | **6** (spring, rest, docker, redis, junit, java) |

→ **LLM 판정 12개 중 6개를 폐기.** "가드를 만들었다"가 아니라 "12개 중 6개를 걸렀다".

---

## §2. 실측 (리허설 실 LLM 1회 — 발표에 쓸 값)

> **아직 미채움.** 리허설에서 배포 Worker에 로드맵 생성을 1회 돌린 뒤, 위 캡처 명령으로 뽑은
> `guard_trace` 로그 한 줄을 아래 코드블록에 붙이고, 표를 그 숫자로 채운다. **"모의" 라벨을 지운다.**

```
(여기에 guard_trace {...} 로그 한 줄 붙여넣기)
```

| 항목 | 값 |
|---|---|
| input_candidates | _ |
| llm_returned | _ |
| dropped_out_of_set | _ |
| dropped_no_evidence | _ |
| dropped_low_confidence | _ |
| dropped_schema | _ |
| dropped_duplicate | _ |
| **accepted** | _ |

→ (LLM 판정 N개 중 M개 폐기 — 실측 채운 뒤 문장 완성)

> STAR 보완(H-2)엔 별도 사실검증 가드가 하나 더 있다([star_enhance.py](../app/llm/star_enhance.py) `has_fabrication`).
