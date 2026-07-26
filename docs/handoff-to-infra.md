# myith-infra 위임 기록

Worker 저장소가 인프라(myith-infra)에 의존하거나, 인프라 쪽 변경이 필요한 항목을 기록한다 (PART L, C-7).

---

## [2026-07-25] ✅ 종료 — 시크릿 환경변수가 worker 컨테이너에 주입되지 않는다

**해결(2026-07-25):** `docker-compose.worker.yml`의 `worker.environment:`에 시크릿 6개가
`${VAR:-}` 형식(미설정 시 빈 문자열)으로 추가됨: `LLM_API_KEY`, `LLM_MODEL`,
`LLM_MODEL_LIGHT`, `NCS_SERVICE_KEY`, `WANTED_API_KEY`, `GITHUB_TOKEN`. O-3 표와 이름 일치 확인.

- Worker 쪽 대응: `${VAR:-}`가 빈 문자열을 주입하므로 `settings.py`가 빈 문자열을 `None`으로
  강등(`_empty_str_to_none`)하고, 모델명은 `llm_model`/`llm_model_light` 프로퍼티로 기본값 폴백.
- **남은 항목(블로커 아님):** `GOOGLE_APPLICATION_CREDENTIALS`(Vision OCR, I-5)는 파일 경로 +
  볼륨 마운트가 필요해 compose에 아직 없음. OCR/Vision(PART 9) 구현 시점에 파일 마운트와 함께 추가.
  그전까지는 OCR 단계 스킵/폴백으로 정상 동작.

---

## [2026-07-25] (원본 기록) 시크릿 환경변수가 worker 컨테이너에 주입되지 않는다

**발단:** PART N 1번(프로젝트 셋업) 후 `docker-compose.worker.yml`과 `settings.py`의 환경변수 계약(O-3)을 대조하던 중 발견.

**저쪽 일인 이유:** C-7 — `docker-compose.worker.yml`은 myith-infra 소유다. Worker는 이 파일을 만들거나 수정하지 않는다.

**현황:**
- `docker-compose.worker.yml`의 `worker.environment:` 블록은 **인프라 주입값 9개**만 전달한다: `DATABASE_URL`, `REDIS_HOST`, `REDIS_PORT`, `RABBITMQ_HOST`, `RABBITMQ_PORT`, `RABBITMQ_USER`, `RABBITMQ_PASSWORD`, `S3_BUCKET`, `AWS_REGION`. → **이 9개는 `settings.py`와 이름이 정확히 일치한다. 문제없음.**
- 그러나 O-3의 **시크릿 7개**(`LLM_API_KEY`, `LLM_MODEL`, `LLM_MODEL_LIGHT`, `NCS_SERVICE_KEY`, `WANTED_API_KEY`, `GITHUB_TOKEN`, `GOOGLE_APPLICATION_CREDENTIALS`)는 compose에 `env_file:`도, 명시 항목도 없어 **컨테이너에 도달하지 않는다.**
- Docker Compose의 디렉토리 `.env`는 `${...}` 치환에만 쓰이고 컨테이너 환경으로 자동 주입되지 않는다.

**결과 (현재도 안전함):** 시크릿이 없으면 `settings.py`가 `None`으로 폴백하고, 해당 기능은 규칙 기반으로 degrade한다(C-3). **컨테이너 기동과 `/health`는 정상.** 즉 지금 배포에는 지장이 없다. 다만 LLM·수집·OCR을 실제로 켜려면 아래가 필요하다.

**저쪽이 제공해야 할 것 (LLM 등 실기능을 켤 때):**
`docker-compose.worker.yml`의 `worker` 서비스에 다음 중 하나를 추가한다.
```yaml
    env_file:
      - .env          # 운영자가 EC2에 둔 .env 의 시크릿을 컨테이너로 전달
```
또는 명시적으로:
```yaml
    environment:
      LLM_API_KEY: ${LLM_API_KEY}
      LLM_MODEL: ${LLM_MODEL}
      LLM_MODEL_LIGHT: ${LLM_MODEL_LIGHT}
      NCS_SERVICE_KEY: ${NCS_SERVICE_KEY}
      WANTED_API_KEY: ${WANTED_API_KEY}
      GITHUB_TOKEN: ${GITHUB_TOKEN}
      GOOGLE_APPLICATION_CREDENTIALS: ${GOOGLE_APPLICATION_CREDENTIALS}
```
`GOOGLE_APPLICATION_CREDENTIALS`는 파일 경로이므로, 자격증명 JSON 파일도 컨테이너에 볼륨 마운트해야 한다.

**Worker 쪽 계약 (구현됨):**
- 필요한 환경변수: 위 시크릿 7개. `app/config/settings.py`가 이 이름들로 읽는다. 없으면 폴백.
- 이름을 바꾸지 않는다. 이 표(O-3)가 계약이다.

**미결 사항:**
- 시크릿 주입을 지금 붙일지, LLM 파이프라인(PART 9) 구현 시점에 붙일지 운영자가 결정.
