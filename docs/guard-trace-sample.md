# 가드 트레이스 — "LLM을 믿지 않는다"의 숫자 근거

역량 추출에서 **LLM이 낸 판정 중 가드가 몇 개를 왜 버렸는지**를 구조화 카운터로 남긴다.
`apply_guards`가 매 실행마다 이 값을 로그로 찍는다([analyzer.py](../app/competency/analyzer.py) — `guard_trace ...`).

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

## 예시 실행값 (⚠️ 모의 입력, 가드 코드는 실제 실행)

> 아래는 백엔드 산출물 **예시 입력(모의 LLM 응답 12건)** 에 **실제 `apply_guards` 코드를 그대로
> 돌린 결과**다. 입력만 모의고 숫자는 가드 로직이 계산한 실값이다. **발표 당일엔 실 LLM 1회 실행값으로
> 이 표를 교체한다**(아래 명령). 숫자를 손으로 만들지 않는다.

| 항목 | 값 |
|---|---|
| input_candidates | 10 |
| llm_returned | **12** |
| dropped_out_of_set | 2 (kubernetes, kafka — 닫힌 목록 밖) |
| dropped_no_evidence | 4 (aws·jpa·typescript·중복spring — 근거가 원문에 실재하지 않음) |
| dropped_low_confidence | 0 |
| accepted | **6** (spring, rest, docker, redis, junit, java) |

→ **LLM 판정 12개 중 6개를 폐기.** "가드를 만들었다"가 아니라 "12개 중 6개를 걸렀다".

## 실측값 캡처 (시연 직전)

배포된 Worker에서 로드맵 생성을 1회 돌린 뒤:

```bash
docker compose -f docker-compose.worker.yml logs worker 2>&1 \
  | grep "guard_trace" | tail -1
```

이 JSON을 위 표에 그대로 붙이고 "예시" 표기를 지운다. **실제 실행값만 발표에 쓴다.**
