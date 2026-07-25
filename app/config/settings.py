"""모든 환경변수와 정책값의 단일 진입점 (C-6, O-3).

규칙:
- 코드 곳곳에서 os.getenv를 부르지 않는다. 여기 한 곳에서만 읽는다.
- 환경변수 이름은 O-3 표 = myith-infra와의 계약이다. 임의로 바꾸지 않는다.
- 시크릿에는 기본값을 두지 않는다(None). 없으면 해당 기능이 폴백된다(C-3).
- 값이 없어도 컨테이너 기동은 성공해야 한다. 여기서 예외를 던지지 않는다.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # ── 시크릿 (운영자 .env, 기본값 없음 → 없으면 폴백) ──────
    LLM_API_KEY: str | None = None
    LLM_MODEL: str = "claude-sonnet-4"  # 설정 기본값 (I-4)
    LLM_MODEL_LIGHT: str = "claude-haiku-4"  # STAR 피드백용 경량 (H-2)
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

    # ── 정책값: 수집·밴딩·재빌드 임계 (F-1, F-7, F-8, F-10) ──
    COLLECT_SAMPLE_SIZE: int = 50
    SKILL_CAP: int = 25
    LEVEL_BAND_MIN: int = 4
    LEVEL_BAND_MAX: int = 7
    PREREQ_THETA: float = 0.3  # F-6 비대칭성 임계
    STAT_WINDOW_MONTHS: int = 6  # F-3 슬라이딩 윈도우
    BUILD_LOCK_TTL_MINUTES: int = 30  # F-0 중복 빌드 방지

    # ── 정책값: LLM 가드 (G-5) ──────────────────────────────
    COMPETENCY_CONFIDENCE_MIN: float = 0.6
    EVIDENCE_MAX_LEN: int = 200
    LLM_SCHEMA_RETRIES: int = 2
    DOC_MIN_CHARS_PER_PAGE: int = 50  # G-4 텍스트 충분 판정
    OCR_CONFIDENCE_MIN: float = 0.6

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
