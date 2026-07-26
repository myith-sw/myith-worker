"""PART N 필수 테스트: O-3 환경변수가 없어도 폴백하고 기동은 성공한다."""

import importlib


def test_settings_load_without_env(monkeypatch):
    # 시크릿·인프라 값이 하나도 없어도 Settings 생성이 실패하지 않는다.
    for var in [
        "DATABASE_URL", "REDIS_HOST", "RABBITMQ_USER", "RABBITMQ_PASSWORD",
        "S3_BUCKET", "LLM_API_KEY", "NCS_SERVICE_KEY", "WANTED_API_KEY",
        "GITHUB_TOKEN", "GOOGLE_APPLICATION_CREDENTIALS",
    ]:
        monkeypatch.delenv(var, raising=False)

    from app.config import settings as settings_module
    importlib.reload(settings_module)
    s = settings_module.Settings(_env_file=None)

    # 시크릿은 기본값 없음(None) → 폴백 대상
    assert s.LLM_API_KEY is None
    assert s.DATABASE_URL is None
    # 계약 기본값
    assert s.RABBITMQ_HOST == "rabbitmq"  # D-7
    assert s.AWS_REGION == "ap-northeast-2"
    # 정책 기본값(F-5)
    assert abs((s.SCORING_WEIGHT_S + s.SCORING_WEIGHT_P + s.SCORING_WEIGHT_N) - 1.0) < 1e-9


def test_async_database_url_conversion():
    from app.config.settings import Settings

    s = Settings(_env_file=None, DATABASE_URL="postgresql://u:p@host:5432/myith")
    assert s.async_database_url == "postgresql+asyncpg://u:p@host:5432/myith"

    s2 = Settings(_env_file=None, DATABASE_URL=None)
    assert s2.async_database_url is None


def test_empty_string_env_treated_as_absent():
    # compose의 ${VAR:-} 가 빈 문자열을 주입해도 폴백이 동작해야 한다.
    from app.config.settings import (
        DEFAULT_LLM_MODEL,
        DEFAULT_LLM_MODEL_LIGHT,
        Settings,
    )

    s = Settings(
        _env_file=None,
        LLM_API_KEY="",
        LLM_MODEL="",
        LLM_MODEL_LIGHT="  ",
        NCS_SERVICE_KEY="",
    )
    assert s.LLM_API_KEY is None
    assert s.NCS_SERVICE_KEY is None
    # 모델명은 빈 문자열이 아니라 기본값으로 폴백
    assert s.llm_model == DEFAULT_LLM_MODEL
    assert s.llm_model_light == DEFAULT_LLM_MODEL_LIGHT

    # 실제 값이 주어지면 그대로 사용
    s2 = Settings(_env_file=None, LLM_MODEL="claude-opus-4")
    assert s2.llm_model == "claude-opus-4"
