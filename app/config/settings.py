"""모든 환경변수와 정책값의 단일 진입점 (C-6, O-3).

규칙:
- 코드 곳곳에서 os.getenv를 부르지 않는다. 여기 한 곳에서만 읽는다.
- 환경변수 이름은 O-3 표 = myith-infra와의 계약이다. 임의로 바꾸지 않는다.
- 시크릿에는 기본값을 두지 않는다(None). 없으면 해당 기능이 폴백된다(C-3).
- 값이 없어도 컨테이너 기동은 성공해야 한다. 여기서 예외를 던지지 않는다.
"""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 모델명 기본값 (I-4, 확정 W2 D-2·D-15). compose가 LLM_MODEL을 빈 문자열로 주입할 수
# 있어 아래 프로퍼티에서 폴백한다. 기존 sonnet-4/haiku-4는 실재하지 않아 400을 낸다.
DEFAULT_LLM_MODEL = "claude-sonnet-5"  # 역량 추출(G-5), Vision(G-4), 문구 개인화(H-1)
DEFAULT_LLM_MODEL_LIGHT = "claude-haiku-4-5"  # AI 보완(H-2), 템플릿 문구(F-9)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # version 미래 필드처럼, 모르는 환경변수는 무시 (D-1)
        case_sensitive=True,
    )

    # ── 앱 메타 ──────────────────────────────────────────────
    APP_NAME: str = "myith-worker"
    APP_ENV: str = "local"  # local | prod
    LOG_LEVEL: str = "INFO"

    # ── 인프라 주입값 (O-3, terraform output) ────────────────
    # 로컬 기동을 위해 기본값을 두되, 없다고 기동이 실패하지 않게 한다.
    DATABASE_URL: str | None = None
    REDIS_HOST: str | None = None
    REDIS_PORT: int = 6379
    RABBITMQ_HOST: str = "rabbitmq"  # compose 서비스명. localhost 아님 (D-7)
    RABBITMQ_PORT: int = 5672
    RABBITMQ_USER: str | None = None
    RABBITMQ_PASSWORD: str | None = None
    S3_BUCKET: str | None = None  # 랜덤 접미어. 하드코딩 금지 (O-3)
    AWS_REGION: str = "ap-northeast-2"

    # ── RabbitMQ 토폴로지 (확정, Core RabbitConfig.java에서 추출) ─────────────
    # 익스체인지 속성이 Core와 한 글자라도 다르면 PRECONDITION_FAILED(406)로 채널 즉사한다.
    # 아래 속성은 Core와 반드시 일치: core.events=topic, worker.fanout=fanout, 둘 다 durable.
    # 작업 큐·DLQ는 Worker가 선언·소유한다(Core는 작업 큐를 선언하지 않는다). 라우팅 키=eventType.
    RABBITMQ_CORE_EXCHANGE: str = "myith.core.events"  # Core→Worker, topic
    RABBITMQ_WORKER_FANOUT: str = "myith.worker.fanout"  # Worker→Core, fanout
    RABBITMQ_QUEUE_AI_ENHANCEMENT: str = "myith.worker.ai-enhancement"
    RABBITMQ_QUEUE_PROFILE_BUILD: str = "myith.worker.profile-build"
    RABBITMQ_QUEUE_ROADMAP: str = "myith.worker.roadmap-generation"  # 우선순위 2에서 소비
    RABBITMQ_DLQ: str = "myith.worker.dlq"

    # ── LLM 공급자 (확정 정정 2026-07-28: Anthropic 직접. D-16 Vertex-우선 대체) ──
    # GCP 결제 프로필이 타인 명의라 통합 이점 소멸 + Vertex 승인 대기가 개발을 막아 직접 API로 전환.
    # 구현체 2개는 LLMProvider 뒤에 유지 → 승인 시 이 값만 "vertex"로 바꾸면 전환된다(I-4).
    LLM_PROVIDER: str = "anthropic"  # "anthropic" | "vertex"
    GCP_PROJECT_ID: str | None = None  # vertex 인증(ADC)용. 승인 시 사용
    GCP_REGION: str = "us-east5"

    # ── 시크릿 (운영자 .env, 기본값 없음 → 없으면 폴백) ──────
    # 모델명은 None으로 두고 아래 프로퍼티에서 기본값으로 폴백한다.
    LLM_API_KEY: str | None = None
    LLM_MODEL: str | None = None  # 설정 기본값 (I-4) → property llm_model
    LLM_MODEL_LIGHT: str | None = None  # 경량 (H-2) → property llm_model_light
    NCS_SERVICE_KEY: str | None = None
    WANTED_API_KEY: str | None = None
    GITHUB_TOKEN: str | None = None
    GOOGLE_APPLICATION_CREDENTIALS: str | None = None

    # ── 리소스 상한 (O-6, 2GB를 RabbitMQ와 나눠 씀) ─────────
    PROCESS_POOL_WORKERS: int = 2
    RABBITMQ_PREFETCH: int = 3
    PDF_MAX_PAGES: int = 30
    PDF_MAX_FILE_MB: int = 10
    HTTP_MAX_CONCURRENCY: int = 10

    # ── 정책값: 난이도 공식 가중치 (F-5, 임의로 바꾸지 않음) ──
    SCORING_WEIGHT_S: float = 0.45
    SCORING_WEIGHT_P: float = 0.30
    SCORING_WEIGHT_N: float = 0.25
    # 표본에 신입수용 신호가 전무하면 S를 이 값으로 폴백 (확정 W2 A-4). 0이 아니라
    # 0.5 = "정보 없음 = 중립". 0이면 "전 직무가 신입 100% 수용"이 되어 D가 왜곡된다.
    SCORING_DEFAULT_S: float = 0.5
    NCS_LEVEL_FALLBACK: int = 4  # 미매핑 스킬 N값 대체 기본 수준 (§1-3)
    NCS_API_DELAY_MS: int = 200  # 자격종목 API 호출 간 지연 (Step 2)

    # ── 정책값: 수집·밴딩·재빌드 임계 (F-1, F-7, F-8, F-10) ──
    COLLECT_SAMPLE_SIZE: int = 50
    SKILL_CAP: int = 25
    # 레이더 축 고정 수 (F-4/F-7). 프론트 레이더가 육각형 고정이라 6으로 묶는다.
    # TODO(F-4): 그룹핑 파이프라인 구현 시 이 값으로 축을 자른다.
    #   초과 → 축별 P합 상위 PROFILE_AXIS_COUNT개만, 잘린 축·스킬을 log로 남긴다(조용히 버리지 않는다).
    #   미만 → 억지로 채우지 않는다. 스킬 없는 축은 완료율이 영구 0%라 다각형이 더 찌그러진다.
    #   자르는 기준이 P합인 이유: 수준(N)으로 자르면 어려운 축만 남아 실무와 멀어진다.
    #   (현재 시드 프로필은 이미 전부 6축이라 런타임 강제 대상 없음. 원티드 실데이터가 흐르면 필요.)
    PROFILE_AXIS_COUNT: int = 6
    LEVEL_BAND_MIN: int = 4
    LEVEL_BAND_MAX: int = 7
    PREREQ_THETA: float = 0.3  # F-6 비대칭성 임계
    STAT_WINDOW_MONTHS: int = 6  # F-3 슬라이딩 윈도우
    BUILD_LOCK_TTL_MINUTES: int = 30  # F-0 중복 빌드 방지

    # ── 정책값: LLM 가드 (G-5) ──────────────────────────────
    COMPETENCY_CONFIDENCE_MIN: float = 0.6
    EVIDENCE_MAX_LEN: int = 200
    LLM_SCHEMA_RETRIES: int = 2

    # ── 정책값: G-3 GitHub 분석 + 외부호출 서킷브레이커 (C-5) ──
    GITHUB_API_TIMEOUT: float = 5.0
    GITHUB_README_MAX_CHARS: int = 8000  # README 상한 (수십만자 저장소 방어)
    GITHUB_MANIFEST_MAX: int = 2  # 최상위 의존성 매니페스트 최대 조회 수
    GITHUB_RETRY_ATTEMPTS: int = 3  # 네트워크 블립 재시도 횟수 (C-6, 하드코딩 금지)
    GITHUB_RETRY_BACKOFF: float = 0.2  # 지수 백오프 배수
    GITHUB_RETRY_MAX_WAIT: float = 2.0  # 백오프 상한
    BREAKER_FAIL_MAX: int = 5  # 연속 실패 임계 → 회로 개방 (GitHub·LLM·Vision 공용)
    BREAKER_RESET_SEC: int = 30  # 개방 후 반개방까지 대기
    DOC_MIN_CHARS_PER_PAGE: int = 50  # G-4 텍스트 충분 판정
    OCR_CONFIDENCE_MIN: float = 0.6
    STAR_MAX_TOKENS: int = 1500  # H-2 STAR 보완 (경량 모델, 짧은 텍스트). effort는 haiku엔 미지원이라 안 씀
    COMPETENCY_MAX_TOKENS: int = 2000  # G-5 역량 추출 (스킬 다수 + evidence 인용)
    LLM_PERSONALIZE_ENABLED: bool = True  # H-1 층2(문구 개인화) on/off. 실패·타임아웃 시 층1로 폴백

    # compose의 `${VAR:-}`는 미설정 시 빈 문자열을 주입한다. 빈 문자열은
    # "제공되지 않음"으로 취급해 None으로 바꾼다 → 폴백이 정상 동작한다 (O-3).
    @field_validator(
        "DATABASE_URL", "REDIS_HOST", "RABBITMQ_USER", "RABBITMQ_PASSWORD",
        "S3_BUCKET", "LLM_API_KEY", "LLM_MODEL", "LLM_MODEL_LIGHT",
        "NCS_SERVICE_KEY", "WANTED_API_KEY", "GITHUB_TOKEN",
        "GOOGLE_APPLICATION_CREDENTIALS", "GCP_PROJECT_ID",
        mode="before",
    )
    @classmethod
    def _empty_str_to_none(cls, v: object) -> object:
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    @property
    def llm_model(self) -> str:
        return self.LLM_MODEL or DEFAULT_LLM_MODEL

    @property
    def llm_model_light(self) -> str:
        return self.LLM_MODEL_LIGHT or DEFAULT_LLM_MODEL_LIGHT

    @property
    def async_database_url(self) -> str | None:
        """SQLAlchemy async 엔진용. postgresql:// → postgresql+asyncpg:// (O-3)."""
        if not self.DATABASE_URL:
            return None
        url = self.DATABASE_URL
        if url.startswith("postgresql+asyncpg://"):
            return url
        if url.startswith("postgresql://"):
            return "postgresql+asyncpg://" + url[len("postgresql://") :]
        if url.startswith("postgres://"):
            return "postgresql+asyncpg://" + url[len("postgres://") :]
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
