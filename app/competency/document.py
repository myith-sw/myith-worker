"""G-4 문서 파싱 — PDF·이미지 3단 하이브리드. 각 단계가 묻는 건 하나: '충분한 텍스트를 얻었나'.

```
1단계  텍스트 추출(pdfplumber/PyMuPDF)   페이지 글자수 ≥ DOC_MIN_CHARS_PER_PAGE → source:"text"
2단계  페이지→이미지 렌더 → OCR           신뢰도 ≥ OCR_CONFIDENCE_MIN & 충분 → source:"ocr"
3단계  Vision LLM(이미지→키워드)          → source:"vision"
4단계  폴백: 페이지 기여 없음(source:"none")
```

**페이지 단위로 판정**한다(텍스트/이미지 페이지가 섞임). **절대 글자 수**로 판정한다 —
"기대 글자 수 대비 커버리지"는 방어 가능한 기대값이 없다(표지 20자, 본문 2000자).

**비용·가용성(시연):** OCR 자격증명이 없으면 2단계는 통째로 스킵(ocr=None) → 1단계→3단계.
Vision은 비싸다($0.3/30p) → **텍스트가 충분한 페이지엔 렌더·Vision을 아예 부르지 않는다.**
페이지 상한(PDF_MAX_PAGES)으로 대용량 문서를 막는다.

이 파서는 스테이지 오케스트레이션(순수 로직)이라 추출기·렌더러·OCR·Vision을 주입받아 단위
테스트한다. 실제 어댑터(pdfplumber/PyMuPDF)는 지연 임포트한다.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from typing import Protocol

from app.config.settings import settings

logger = logging.getLogger("myith.competency.document")


@dataclass(frozen=True)
class OcrResult:
    text: str
    confidence: float


class OcrProvider(Protocol):
    async def extract_text(self, image: bytes) -> OcrResult | None: ...


class VisionExtractor(Protocol):
    async def extract_keywords(self, image: bytes) -> str: ...  # "" on fail


@dataclass(frozen=True)
class DocPage:
    text: str
    source: str  # "text" | "ocr" | "vision" | "none"


@dataclass
class DocResult:
    text: str
    pages: list[DocPage] = field(default_factory=list)

    @property
    def has_text(self) -> bool:
        return bool(self.text.strip())


class DocumentParser:
    """3단 하이브리드 오케스트레이션. 추출기·렌더러·OCR·Vision을 주입받는다.

    extract_page_texts(data) -> list[str]  : 1단계 페이지별 텍스트(이미지 파일이면 [""]).
    render_page(data, i)      -> bytes|None: 2·3단계용 페이지 이미지(필요할 때만 호출).
    ocr, vision               : None이면 해당 단계 스킵.
    """

    def __init__(
        self,
        *,
        extract_page_texts,
        render_page,
        ocr: OcrProvider | None = None,
        vision: VisionExtractor | None = None,
        min_chars: int | None = None,
        ocr_conf_min: float | None = None,
        max_pages: int | None = None,
    ) -> None:
        self._extract_page_texts = extract_page_texts
        self._render_page = render_page
        self._ocr = ocr
        self._vision = vision
        self._min_chars = settings.DOC_MIN_CHARS_PER_PAGE if min_chars is None else min_chars
        self._ocr_conf_min = settings.OCR_CONFIDENCE_MIN if ocr_conf_min is None else ocr_conf_min
        self._max_pages = settings.PDF_MAX_PAGES if max_pages is None else max_pages

    async def parse(self, data: bytes) -> DocResult:
        try:
            page_texts = self._extract_page_texts(data)
        except Exception as e:  # noqa: BLE001 — 손상 파일 등. 파이프라인 안 죽임(C-3)
            logger.warning("문서 텍스트 추출 실패 → 빈 결과: %s", e)
            return DocResult(text="", pages=[])

        pages: list[DocPage] = []
        for i, raw in enumerate(page_texts[: self._max_pages]):
            pages.append(await self._parse_page(data, i, raw))
        combined = "\n".join(p.text for p in pages if p.text)
        return DocResult(text=combined, pages=pages)

    async def _parse_page(self, data: bytes, i: int, raw: str) -> DocPage:
        text = (raw or "").strip()
        if len(text) >= self._min_chars:  # 1단계: 텍스트 충분 → 렌더·Vision 안 부름(비용)
            return DocPage(text, "text")

        image = self._safe_render(data, i)
        if image is None:
            return DocPage("", "none")

        if self._ocr is not None:  # 2단계: OCR (자격증명 없으면 ocr=None → 스킵)
            try:
                r = await self._ocr.extract_text(image)
            except Exception as e:  # noqa: BLE001
                logger.warning("OCR 실패 → 다음 단계: %s", e)
                r = None
            if r and r.confidence >= self._ocr_conf_min and len(r.text.strip()) >= self._min_chars:
                return DocPage(r.text.strip(), "ocr")

        if self._vision is not None:  # 3단계: Vision LLM (비쌈 — 텍스트 부족 페이지만)
            try:
                kw = await self._vision.extract_keywords(image)
            except Exception as e:  # noqa: BLE001
                logger.warning("Vision 실패 → 폴백: %s", e)
                kw = ""
            if kw and kw.strip():
                return DocPage(kw.strip(), "vision")

        return DocPage("", "none")  # 4단계: 이 페이지는 기여 없음

    def _safe_render(self, data: bytes, i: int) -> bytes | None:
        try:
            return self._render_page(data, i)
        except Exception as e:  # noqa: BLE001
            logger.warning("페이지 렌더 실패 → 스킵: %s", e)
            return None


# ── 실제 어댑터 (지연 임포트) ──────────────────────────────────────────────


def pdf_page_texts(data: bytes) -> list[str]:
    """pdfplumber로 페이지별 텍스트. 대용량은 상한 페이지까지만 연다."""
    import pdfplumber

    out: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages[: settings.PDF_MAX_PAGES]:
            out.append(page.extract_text() or "")
    return out


def render_pdf_page(data: bytes, i: int) -> bytes | None:
    """PyMuPDF로 i번째 페이지를 PNG로 렌더. 필요할 때만 호출된다."""
    import fitz  # PyMuPDF

    with fitz.open(stream=data, filetype="pdf") as doc:
        if i >= doc.page_count:
            return None
        pix = doc.load_page(i).get_pixmap(dpi=settings.PDF_RENDER_DPI)
        return pix.tobytes("png")


def image_as_single_page(data: bytes):
    """이미지 파일(PDF 아님)을 '텍스트 없는 1페이지'로. 렌더는 원본 바이트를 그대로 준다."""
    return [""], (lambda _data, _i: data)


def _is_pdf(data: bytes, file_key: str) -> bool:
    return data[:5] == b"%PDF-" or file_key.lower().endswith(".pdf")


class S3Fetcher(Protocol):
    async def fetch(self, key: str, max_bytes: int) -> bytes | None: ...


class DocumentSource:
    """fileKey → S3 바이트 → DocumentParser → 텍스트. roadmap 컨슈머가 주입받는다.

    파일은 **S3에서만** 가져오고(G-4, Presigned 발급은 Core), 메모리로만 처리한다 — 임시 파일을
    디스크에 쓰지 않으므로 누수 위험이 없다(t3.small 20GB 공유). 크기 상한(PDF_MAX_FILE_MB)으로
    대용량을 막고, 실패·빈 결과는 ""로 degrade한다(C-3). PDF/이미지는 매직바이트·확장자로 가른다.
    """

    def __init__(
        self,
        s3_fetcher: S3Fetcher,
        *,
        ocr: OcrProvider | None = None,
        vision: VisionExtractor | None = None,
    ) -> None:
        self._s3 = s3_fetcher
        self._ocr = ocr
        self._vision = vision

    async def fetch_and_parse(self, file_key: str) -> str:
        if not isinstance(file_key, str) or not file_key:
            return ""
        max_bytes = settings.PDF_MAX_FILE_MB * 1024 * 1024
        data = await self._s3.fetch(file_key, max_bytes)
        if not data:
            return ""
        if _is_pdf(data, file_key):
            parser = DocumentParser(
                extract_page_texts=pdf_page_texts,
                render_page=render_pdf_page,
                ocr=self._ocr,
                vision=self._vision,
            )
        else:
            texts, render = image_as_single_page(data)
            parser = DocumentParser(
                extract_page_texts=lambda _d: texts,
                render_page=render,
                ocr=self._ocr,
                vision=self._vision,
            )
        result = await parser.parse(data)
        if not result.has_text:
            return ""
        return f"[업로드 문서]\n{result.text}"
