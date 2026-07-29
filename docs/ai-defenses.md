# 방어 기법 — "라이브러리를 썼다"가 아니라 "깨지는 걸 발견하고 직접 만들었다"

MYiTH Worker가 적대적 리뷰(다중 에이전트)까지 돌리며 만든 방어 장치. **사실만 기록한다.**

| 방어 | 발견 경위 | 조치 | 검증 방법 | 코드 위치 |
|---|---|---|---|---|
| **AsyncCircuitBreaker (자체)** | 서킷브레이커로 `pybreaker`를 붙였는데, 그 `call_async`가 **Tornado `gen.coroutine` 기반**이라 순수 asyncio에서 회로가 열리는 순간 `NameError: gen`으로 죽었다. MockTransport 테스트에서 커밋 전에 발견. | 자체 `AsyncCircuitBreaker` 구현(open/half-open/closed, 상태 문자열 동일). `requirements`에서 pybreaker 제거, 주석으로 재도입 방지. | 429 반복 → 회로 OPEN → 즉시 스킵을 테스트로 고정 | [breaker.py](../app/resilience/breaker.py) |
| **LLM 서킷브레이커 + 실호출 검증** | 리뷰가 "LLM 경로에 브레이커가 아예 없다(C-5 위반)"를 지적. 선불 $5라 402·429가 실제 시나리오. | 모든 async 외부호출(LLM·GitHub·Vision)에 브레이커. | **잘못된 키로 api.anthropic.com에 실제 401**을 내서 역량추출 []·STAR FAILED·문구 층1 폴백을 실측(2026-07-29) | [provider.py](../app/llm/provider.py) |
| **프롬프트 인젝션 이중 방어(4경로)** | Core가 "지시부와 사용자 입력이 같은 user 메시지에 있다"고 지적. README·PDF는 공격자가 자기 저장소에 인젝션을 심을 수 있는 통로. | 지시부를 Anthropic **`system` 파라미터**로 분리(STAR·역량·문구·Vision 4경로 전부) + STAR 원문의 `<,>` **이스케이프**(`</situation>` 탈출 차단). `system` 미전달 시 요청 동일(회귀 안전). | system 분리·이스케이프·회귀를 테스트로 고정. 적대적 리뷰 확정 0건 | [provider.py](../app/llm/provider.py) · [star_enhance.py](../app/llm/star_enhance.py) |
| **멱등 선점-후-보상삭제** | 리뷰가 "eventId를 선점 후 발행 실패 시, 재처리가 중복으로 스킵돼 COMPLETED도 FAILED도 영영 안 나감 → 프론트 무한 폴링"을 지적(H-2 FAILED-always 위반). | dispatch 실패 시 **선점을 해제(보상)** → DLQ 재처리가 재시도 가능. 재발행 eventId가 결정론적이라 중복돼도 Core가 접음. | 보상 삭제 경로를 코드로 반영, 적대적 리뷰 확정 | [base.py](../app/consumers/base.py) |
| **결정론적 eventId** | RabbitMQ at-least-once라 재발행이 발생. Core가 봉투 eventId로 멱등 처리(W2 C-3). | 발신 eventId = `uuid5(고정NS, eventType:대상ID)` → **재발행해도 동일** → Core에서 중복 안 생김. requestId(Core값)와 다른 값. | 재발행 동일성·requestId≠eventId 테스트 | [envelope.py](../app/messaging/envelope.py) |
| **와이어 봉투 헤더/본문** | 문서 D-1은 봉투를 body JSON이라 했으나, Core 실구현은 eventId·eventType·traceId가 **AMQP 헤더**, body는 payload 자체. `json.loads(body)["eventId"]`는 KeyError. | 발신은 헤더+payload본문, 수신은 헤더에서 읽기. 문서(D-1) 정정. | 리뷰(와이어 형식 관점) 0건 | [fanout.py](../app/publishers/fanout.py) · [base.py](../app/consumers/base.py) |
| **가드2 numeric 전환** | QA "AI 보완 시 R이 빈다". 배포 로그는 SSM 접근 없어 못 얻어 **코드로 재현**: strict가 `리액트→React`·`도커→Docker` 같은 정상 첨삭을 날조로 판정 → `enhancedStar=null`. | 사실검증 기본을 **numeric(숫자만)** 으로. 수치 조작은 유지, 표기 변환 오탐 제거. `STAR_FABRICATION_CHECK` 설정. | 한↔영 표기·수치조작·off/strict를 테스트로 고정 | [star_enhance.py](../app/llm/star_enhance.py) |
| **STAR 원문 유지(글 유실 방지)** | PM "짧게 쓴 글이 AI 보완 적용 시 사라진다". AI가 무의미한 항목을 빈 값으로 반환 → 원문 삭제. | 원문이 있는데 AI가 빈 값을 주면 **원문 유지**. 빈 항목은 공백(창작 금지). | 원문 유지·공백 유지·다듬기 반영 테스트 | [star_enhance.py](../app/llm/star_enhance.py) |
| **S3 스트림-read 가드 + 메모리 전용** | 리뷰가 "`get_object`는 감쌌지만 스트림 `.read()`가 guard 밖 → 중간 실패 시 DLQ(C-3 위반)"를 지적. | read를 guard 안으로(중간 실패→''). 파일을 **디스크에 안 쓰고 메모리로만** 처리(임시파일 0). 크기 상한. | 스트림 중간실패·상한초과 → None 테스트 | [s3.py](../app/storage/s3.py) |
| **SSRF 방어** | GitHub 분석에 사용자 URL이 들어옴. | host가 `github.com`만 통과. IP 리터럴(169.254.169.254 등) 거부. | SSRF·형식오류 파라미터 테스트 | [github.py](../app/competency/github.py) |
| **Vision 비용 제어 + MAX_EXPERIENCES** | 리뷰가 "파일 다수 × Vision 페이지로 $5 예산 폭발" 가능을 지적. | 텍스트 충분한 페이지엔 Vision 미호출. experiences 상한. media_type 매직바이트 판별(jpg 대응). | 비용경로·상한 테스트 | [document.py](../app/competency/document.py) |
| **가드 트레이스** | "가드를 만들었다"보다 "12개 중 6개 폐기"가 설득력. | `apply_guards`가 폐기 사유별 구조화 카운터를 로그로 남김(계약·DB 변경 0). | 사유별 카운트 테스트 | [analyzer.py](../app/competency/analyzer.py) |
| **evidence 대조범위 확장** | evidence를 AI 보완에 주입하면, 가드가 STAR 원문만 대조해 evidence 반영분을 날조로 폐기함. | 사실검증 대조 기준에 **evidence 포함**(3-4). DB 조회 실패는 근거 없이 진행(AI 보완 안 죽임). | evidence 숫자 반영·nullable·DB예외 테스트 | [star_enhance.py](../app/llm/star_enhance.py) |
| **시드 --prune** | 시드 로더가 upsert만 해 옛 시드의 유령 행이 남음(유령 직무·F-4 위반). | `--prune`으로 시드에 없는 job·skill_ncs_map 삭제. 빈시드 전체삭제 방지 가드. | 유령·F-4·빈시드 라운드트립 테스트 | [skill_map_loader.py](../app/ncs/skill_map_loader.py) |

> **핵심 메시지:** 라이브러리를 붙인 게 아니라, **라이브러리가 우리 asyncio 환경에서 깨지는 걸
> 발견하고 직접 만들었다.** LLM 실패는 실제 401 응답으로 검증했다. 적대적 리뷰가 잡은 실결함은
> 전부 반영했다.
