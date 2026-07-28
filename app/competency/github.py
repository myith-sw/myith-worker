"""G-3 GitHub 저장소 분석 — clone하지 않는다. 공개 저장소만, 실패는 조용히 스킵.

API 3종만 쓴다: languages(언어 비율) · readme(base64) · contents(최상위 → 매니페스트 1~2개).
결과는 라벨링된 텍스트로 만들어 **G-2와 같은 analyzer**로 흘려보낸다(별도 LLM 경로 없음).

방어(C-4·C-5·SSRF):
- host는 `github.com`만 허용, owner/repo를 못 뽑으면 스킵(SSRF 차단).
- 404·비공개·기타 4xx → **None 반환**(스킵, 회로 영향 없음). 403·429·5xx·타임아웃·네트워크
  → 예외 → 서킷브레이커 실패로 카운트. 회로가 열리면 즉시 스킵(파이프라인 안 죽임, C-3).
- README·매니페스트 텍스트는 호출부(analyzer)의 데이터 영역에 들어가 지시로 해석되지 않는다(C-4).
- README 상한(GITHUB_README_MAX_CHARS)으로 수십만 자 저장소를 방어한다.
- `GITHUB_TOKEN` 없이도 동작한다(미인증 60/시간). 429는 브레이커로 흡수.
"""

from __future__ import annotations

import base64
import logging
import re
from urllib.parse import urlparse

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config.settings import settings
from app.resilience.breaker import AsyncCircuitBreaker, CircuitOpenError, get_breaker

logger = logging.getLogger("myith.competency.github")

_MANIFESTS = {
    "package.json",
    "build.gradle",
    "build.gradle.kts",
    "requirements.txt",
    "pyproject.toml",
    "go.mod",
    "pom.xml",
}
_REPO_RE = re.compile(r"^/([^/]+)/([^/]+)")


class _Transient(Exception):
    """장애(403/429/5xx). 서킷브레이커 실패로 센다."""


def parse_repo(url: str) -> tuple[str, str] | None:
    """github.com URL에서 (owner, repo)를 뽑는다. 아니면 None(SSRF·형식 오류 → 스킵).

    허용: https://github.com/o/r, 끝 슬래시, `.git`, `/tree/main`, `/o/r/...`.
    거부: github.com 아닌 호스트, owner/repo 누락.
    """
    if not url or not isinstance(url, str):
        return None
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return None
    if parsed.hostname not in ("github.com", "www.github.com"):
        return None  # SSRF 방어: github.com만
    m = _REPO_RE.match(parsed.path)
    if not m:
        return None
    owner, repo = m.group(1), m.group(2)
    if repo.endswith(".git"):
        repo = repo[:-4]
    if not owner or not repo:
        return None
    return owner, repo


def _decode_b64(node: dict, cap: int) -> str:
    """GitHub content 응답의 base64를 디코드하고 상한 적용."""
    if not isinstance(node, dict) or node.get("encoding") != "base64":
        return ""
    try:
        raw = base64.b64decode(node.get("content") or "")
        return raw.decode("utf-8", errors="ignore")[:cap]
    except (ValueError, TypeError):
        return ""


def _format_evidence(owner: str, repo: str, langs: dict, readme: str, manifests: str) -> str:
    lines = [f"[GitHub 저장소 {owner}/{repo}]"]
    if isinstance(langs, dict) and langs:
        total = sum(v for v in langs.values() if isinstance(v, (int, float))) or 1
        share = ", ".join(
            f"{k} {round(100 * v / total)}%" for k, v in langs.items() if isinstance(v, (int, float))
        )
        lines.append(f"언어: {share}")
    if readme:
        lines += ["README:", readme]
    if manifests:
        lines += ["의존성 매니페스트:", manifests]
    return "\n".join(lines)


class HttpxGitHubClient:
    """httpx 기반 GitHubClient. fetch_repo_evidence(url) → 텍스트 | None(스킵)."""

    def __init__(self, *, token: str | None = None, client_factory=None, breaker=None) -> None:
        self._token = token
        self._client_factory = client_factory or self._default_client_factory
        self._breaker: AsyncCircuitBreaker = breaker or get_breaker("github")

    def _default_client_factory(self) -> httpx.AsyncClient:
        headers = {"Accept": "application/vnd.github+json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"  # GitHub는 Bearer
        return httpx.AsyncClient(
            base_url="https://api.github.com",
            headers=headers,
            timeout=settings.GITHUB_API_TIMEOUT,
        )

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),  # 네트워크 블립만 재시도
        stop=stop_after_attempt(settings.GITHUB_RETRY_ATTEMPTS),
        wait=wait_exponential(
            multiplier=settings.GITHUB_RETRY_BACKOFF, max=settings.GITHUB_RETRY_MAX_WAIT
        ),
        reraise=True,
    )
    async def _get(self, client: httpx.AsyncClient, path: str) -> httpx.Response | None:
        """200→Response, 404·기타4xx→None(스킵), 403/429/5xx→_Transient(브레이커 실패)."""
        resp = await client.get(path)
        sc = resp.status_code
        if sc == 200:
            return resp
        if sc in (403, 429) or sc >= 500:
            raise _Transient(f"{path} → {sc}")
        return None  # 404(없음/비공개) 및 기타 4xx → 스킵, 실패 아님

    async def _fetch(self, owner: str, repo: str) -> str | None:
        async with self._client_factory() as client:
            langs_resp = await self._get(client, f"/repos/{owner}/{repo}/languages")
            if langs_resp is None:
                return None  # 저장소 없음/비공개 → 전체 스킵
            langs = langs_resp.json()

            readme = ""
            readme_resp = await self._get(client, f"/repos/{owner}/{repo}/readme")
            if readme_resp is not None:
                readme = _decode_b64(readme_resp.json(), settings.GITHUB_README_MAX_CHARS)

            manifests = await self._fetch_manifests(client, owner, repo)
        return _format_evidence(owner, repo, langs, readme, manifests)

    async def _fetch_manifests(self, client: httpx.AsyncClient, owner: str, repo: str) -> str:
        resp = await self._get(client, f"/repos/{owner}/{repo}/contents/")
        if resp is None:
            return ""
        try:
            entries = resp.json()
        except ValueError:
            return ""
        picked = [
            e for e in entries
            if isinstance(e, dict) and e.get("type") == "file" and e.get("name") in _MANIFESTS
        ][: settings.GITHUB_MANIFEST_MAX]
        out: list[str] = []
        for entry in picked:
            file_resp = await self._get(client, f"/repos/{owner}/{repo}/contents/{entry['path']}")
            if file_resp is not None:
                text = _decode_b64(file_resp.json(), settings.GITHUB_README_MAX_CHARS)
                if text:
                    out.append(f"# {entry['name']}\n{text}")
        return "\n".join(out)

    async def fetch_repo_evidence(self, repo_url: str) -> str | None:
        """공개 저장소 요약 텍스트. 실패·비공개·404·회로개방 → None(조용히 스킵)."""
        parsed = parse_repo(repo_url)
        if not parsed:
            logger.info("repoUrl 파싱 실패/비-github → 스킵: %r", repo_url)
            return None
        owner, repo = parsed
        try:
            return await self._breaker.call_async(self._fetch, owner, repo)
        except CircuitOpenError:
            logger.warning("GitHub 서킷 개방 → 스킵: %s/%s", owner, repo)
            return None
        except Exception as e:  # noqa: BLE001 — 타임아웃·5xx·429 등. 파이프라인을 죽이지 않는다(C-3)
            logger.warning("GitHub 조회 실패 → 스킵 %s/%s: %s", owner, repo, e)
            return None
