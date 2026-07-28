"""G-3 GitHub 클라이언트 테스트. 실제 GitHub 없이 httpx.MockTransport로 검증."""

import asyncio
import base64

import httpx
import pytest

from app.competency.github import (
    HttpxGitHubClient,
    _decode_b64,
    _format_evidence,
    parse_repo,
)
from app.resilience.breaker import AsyncCircuitBreaker


def _run(coro):
    return asyncio.run(coro)


def _b64(s: str) -> str:
    return base64.b64encode(s.encode()).decode()


# ── parse_repo: SSRF 방어 + 형식 관용 ──────────────────────────────────────


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://github.com/o/r", ("o", "r")),
        ("https://github.com/o/r/", ("o", "r")),
        ("https://github.com/o/r.git", ("o", "r")),
        ("https://github.com/o/r/tree/main", ("o", "r")),
        ("https://www.github.com/o/r", ("o", "r")),
    ],
)
def test_parse_repo_accepts_valid_forms(url, expected):
    assert parse_repo(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.com/o/r",  # SSRF: 다른 호스트
        "https://gitlab.com/o/r",
        "https://github.com/o",  # repo 없음
        "https://github.com/",
        "http://169.254.169.254/o/r",  # 메타데이터 SSRF
        "",
        None,
    ],
)
def test_parse_repo_rejects_non_github_or_malformed(url):
    assert parse_repo(url) is None


# ── _decode_b64: 상한 + 방어 ───────────────────────────────────────────────


def test_decode_b64_caps_length():
    assert _decode_b64({"encoding": "base64", "content": _b64("Hello World")}, 5) == "Hello"


def test_decode_b64_non_base64_returns_empty():
    assert _decode_b64({"encoding": "none", "content": "x"}, 100) == ""
    assert _decode_b64({}, 100) == ""


def test_format_evidence_language_percent():
    txt = _format_evidence("o", "r", {"Python": 8000, "JavaScript": 2000}, "리드미", "")
    assert "Python 80%" in txt and "JavaScript 20%" in txt and "리드미" in txt


# ── fetch_repo_evidence via MockTransport ──────────────────────────────────


def _factory(handler):
    def make():
        return httpx.AsyncClient(
            base_url="https://api.github.com", transport=httpx.MockTransport(handler)
        )

    return make


def _ok_handler(request):
    p = request.url.path
    if p.endswith("/languages"):
        return httpx.Response(200, json={"Python": 8000, "JavaScript": 2000})
    if p.endswith("/readme"):
        return httpx.Response(200, json={"encoding": "base64", "content": _b64("React로 대시보드를 구현했다")})
    if p.endswith("/contents/"):
        return httpx.Response(200, json=[{"type": "file", "name": "package.json", "path": "package.json"}])
    if p.endswith("/contents/package.json"):
        return httpx.Response(200, json={"encoding": "base64", "content": _b64('{"react":"18"}')})
    return httpx.Response(404)


def _fresh_breaker(fail_max=5):
    return AsyncCircuitBreaker(fail_max=fail_max, reset_timeout=30, name="test")


def test_fetch_success_includes_langs_readme_manifest():
    client = HttpxGitHubClient(client_factory=_factory(_ok_handler), breaker=_fresh_breaker())
    text = _run(client.fetch_repo_evidence("https://github.com/o/r"))
    assert text is not None
    assert "Python 80%" in text
    assert "React로 대시보드를 구현했다" in text
    assert "package.json" in text and "react" in text


def test_fetch_404_languages_returns_none():
    def h(request):
        return httpx.Response(404)

    client = HttpxGitHubClient(client_factory=_factory(h), breaker=_fresh_breaker())
    assert _run(client.fetch_repo_evidence("https://github.com/o/r")) is None


def test_fetch_non_github_url_skips_without_call():
    client = HttpxGitHubClient(client_factory=_factory(_ok_handler), breaker=_fresh_breaker())
    assert _run(client.fetch_repo_evidence("https://evil.com/o/r")) is None


def test_rate_limit_429_skips_and_opens_breaker():
    def h(request):
        return httpx.Response(429, json={"message": "rate limited"})

    breaker = _fresh_breaker(fail_max=2)
    client = HttpxGitHubClient(client_factory=_factory(h), breaker=breaker)
    # 2회 실패로 회로 개방, 3회차는 즉시 스킵. 전부 None(파이프라인 안 죽음).
    for _ in range(3):
        assert _run(client.fetch_repo_evidence("https://github.com/o/r")) is None
    assert breaker.current_state == "open"


def test_readme_missing_still_returns_langs():
    def h(request):
        p = request.url.path
        if p.endswith("/languages"):
            return httpx.Response(200, json={"Go": 100})
        return httpx.Response(404)  # readme·contents 없음

    client = HttpxGitHubClient(client_factory=_factory(h), breaker=_fresh_breaker())
    text = _run(client.fetch_repo_evidence("https://github.com/o/r"))
    assert text is not None and "Go 100%" in text


# ── 토큰 헤더 (없어도 동작) ─────────────────────────────────────────────────


def test_default_client_omits_auth_without_token():
    client = HttpxGitHubClient(token=None)
    c = client._default_client_factory()
    try:
        assert "Authorization" not in c.headers
    finally:
        _run(c.aclose())


def test_default_client_uses_bearer_with_token():
    client = HttpxGitHubClient(token="ght_x")
    c = client._default_client_factory()
    try:
        assert c.headers["Authorization"] == "Bearer ght_x"
    finally:
        _run(c.aclose())
