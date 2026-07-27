# myith-core 위임 기록

Worker가 Core에 의존하거나, Core 쪽 변경이 필요한 항목을 기록한다 (PART L, C-1).

---

## [2026-07-26] 공유 테이블 DDL을 Worker Alembic으로 이관 — Core Flyway 정리 필요

**발단:** 확정 D-13/W2. Core Flyway가 만들던 공유 테이블 5개를 Worker Alembic이 소유하게 됨.

**저쪽(Core) 일인 이유:** 같은 DB(`myith`)를 공유하는데 두 마이그레이터가 같은 테이블을
만들면 충돌한다. DDL 소유권을 한쪽으로 모아야 한다.

### Core가 해야 할 것

1. **`V1__init_schema.sql`에서 아래 5개 테이블의 `CREATE TABLE`(+인덱스)을 제거한다.**
   이 테이블들의 DDL은 이제 Worker Alembic이 소유한다:
   `job`, `job_profile`, `ncs_unit`, `ncs_certification`, `user_competency`
2. **`V2__seed_data.sql`을 삭제한다.** 시드는 이제 Worker `python -m app.seed.load_all`이
   유일한 출처다(job·job_profile·ncs_unit·ncs_certification·skill_ncs_map).
3. **읽기 전용 엔티티는 유지**하되 `@Immutable`로 두고, 아래 컬럼 계약과 **정확히 일치**시킨다.
   Core는 `ddl-auto: validate`이므로 컬럼명·타입이 어긋나면 **기동에 실패한다**.
4. Core가 소유·생성하는 테이블(users, roadmap, quest, character, star_record,
   dashboard_snapshot, user_diagnosis, outbox, **processed_event**)의 DDL은 **그대로 둔다.**
   특히 `processed_event`는 Core 소유다 — Worker는 별도 `worker_processed_event`를 쓴다.

### 컬럼 계약 (Worker Alembic이 만드는 실제 스키마 = Core 읽기 전용 엔티티가 맞춰야 할 것)

```
job                (PK job_code)
  job_code varchar, job_name varchar, category_code varchar, category_name varchar,
  tagline text, ncs_detail_code varchar null

job_profile        (PK job_code, version)
  job_code varchar, version int,
  axes jsonb, skills jsonb, levels jsonb, prerequisites jsonb,
  questions jsonb, quest_templates jsonb, activity_quests jsonb,
  built_at timestamptz

ncs_unit           (PK code)
  code varchar, name varchar, description text, level int,
  is_verified boolean not null default false,
  major_name varchar, middle_name varchar, minor_name varchar, detail_name varchar

ncs_certification  (PK ncs_unit_code, cert_code)
  ncs_unit_code varchar, cert_code varchar, cert_name varchar, unit_type varchar

user_competency    (PK roadmap_id, skill_code)
  roadmap_id bigint, skill_code varchar,
  mastery numeric(3,2), evidence text, confidence numeric(3,2), created_at timestamptz
```

> `ncs_unit.is_verified`, `job.ncs_detail_code`는 이번에 새로 생긴 컬럼이다. Core 엔티티가
> 이 컬럼을 몰라도 validate는 통과하지만(엔티티에 없는 컬럼은 무시), **엔티티가 있는데 DB에
> 없으면 실패한다.** 즉 Core는 위 컬럼의 **부분집합**만 매핑하면 된다.
>
> `job`에는 `available` 컬럼이 **없다** — Core가 `job_profile` 존재 여부로 파생한다
> (`JobQueryService.profile.isPresent()`). Worker 시드 `job.json`의 `available`은 DB에 저장하지 않는다.

### 배포 실행 순서 (반드시 지킬 것)

```bash
# 0) 개발 DB 리셋 (Flyway checksum 충돌 회피)
psql "$DATABASE_URL" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

# 1) Worker 먼저 — 공유 테이블 + 시드
cd myith-worker && alembic upgrade head && python -m app.seed.load_all

# 2) Core — Core 소유 테이블만
cd ../myith-core && ./gradlew flywayMigrate   # 또는 기동 시 자동

# 3) Core 기동 (ddl-auto: validate 통과)
```

**Worker가 먼저 돌지 않으면** Core의 `validate`가 `job_profile`·`ncs_unit` 등 읽기 전용
엔티티를 검증하다 테이블이 없어 **기동에 실패한다.** 컨테이너 배포면 Core 기동 전에
Worker 마이그레이션 잡을 한 번 돌리는 형태가 안전하다.

### ⚠ 만약 Core를 H2 인메모리로 띄우고 있다면

그 경우 Core의 Flyway/validate는 **H2(별도 DB)** 에서 돌아 Worker의 Postgres와 부딪히지
않는다 — 대신 Core가 `job_profile`·`user_competency` 등 **Worker 데이터를 볼 수 없다.**
통합 시연을 하려면 Core도 **같은 RDS Postgres(`myith`)** 를 바라봐야 하고, 그때 위 순서가
적용된다. (H2는 Core 단독 로컬 테스트용, 통합 배포는 공유 Postgres)

**Worker 쪽 계약 (구현·푸시됨, feat/#5-ncs-real-data):**
- 위 5개 테이블 + skill_stat·unmapped_skill·job_profile_build_lock·collection_cursor·
  worker_processed_event·ncs_load_cursor(총 12개)를 Alembic이 만든다.
- 시드: `app/seed/load_all` (job 10개, job_profile 10개×6축, ncs_unit 265, skill_ncs_map 112,
  ncs_certification 600행→로더 dedup 521). **자격 연계도 시드로 적재한다**(확정 A안, W2 D-3 대체).
  job_profile.json 최상위 키는 camelCase, JSONB 중첩 내용도 camelCase(Core 계약). guidance는 4종.

**미결(Core가 결정):**
- Core 배포 DB가 H2 인메모리인지 공유 RDS Postgres인지. 통합엔 후자가 필요.

---

## [2026-07-27] AI 보완(STAR) 결과 조회 — Core 타임아웃 안전망 필요 (무한 폴링 방지)

**발단:** Core `origin/dev` 실측(시드 가이드 AI). `AiEnhancementController.getResult()`가 결과가
없으면 **무조건 `PROCESSING`을 반환**하고 **타임아웃이 없다.** Worker가 `AiEnhancementCompleted`를
발행하지 못하면(장애·미구현·큐 유실) 프론트가 **영원히 폴링**한다 — STAR 피드백 스피너가 안 멈춘다.

**저쪽(Core) 일인 이유:** 결과 저장소(`resultStore`)·폴링 API·SSE 연결을 Core가 소유한다
(C-7의 반대 방향 — Worker가 관여할 수 없는 영역).

**Core가 해야 할 것:**
- AiEnhancement 요청 시각을 기록하고, `getResult`가 **N초 초과 시 `FAILED` + `errorCode:"AI_TIMEOUT"`**
  을 반환하게 한다. Worker가 죽어도 화면이 멈추지 않아야 한다. (로드맵 생성은 `ConsistencyScheduler`
  안전망이 이미 있으나, AI 보완 경로엔 없다.)

**Worker 쪽 계약 (구현 예정 — 우선순위 1):**
- `consumers/ai_enhancement.py`가 `AiEnhancementRequested` 소비 → `AiEnhancementCompleted` 발행.
  **성공·실패 모두 발행**(실패도 `status:"FAILED"`+`errorCode`, `enhancedStar:null`, `feedback:[]`).
  `requestId`·`roadmapId` 필수, 봉투 `eventId`는 재발행 시 **동일 값**(Core `processed_event` 멱등).

**미결:** Core의 타임아웃 N초 값.
