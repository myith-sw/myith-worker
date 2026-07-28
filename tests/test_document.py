"""G-4 문서 3단 하이브리드 테스트. pdfplumber·Vision·S3 없이 주입식으로 스테이지 로직 검증."""

import asyncio

from app.competency.document import (
    DocumentParser,
    DocumentSource,
    OcrResult,
)


def _run(coro):
    return asyncio.run(coro)


class RenderSpy:
    def __init__(self, img: bytes = b"IMG"):
        self.img = img
        self.calls = 0

    def __call__(self, data, i):
        self.calls += 1
        return self.img


class FakeOcr:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    async def extract_text(self, image):
        self.calls += 1
        return self.result


class FakeVision:
    def __init__(self, kw: str):
        self.kw = kw
        self.calls = 0

    async def extract_keywords(self, image):
        self.calls += 1
        return self.kw


def _parser(texts, **kw):
    return DocumentParser(extract_page_texts=lambda _d: texts, **kw)


# ── 🔴 비용: 텍스트 충분하면 렌더·Vision을 아예 안 부른다 ──────────────────


def test_text_sufficient_skips_render_and_vision():
    render, vision = RenderSpy(), FakeVision("kw")
    p = _parser(["a" * 100], render_page=render, vision=vision, min_chars=50)
    r = _run(p.parse(b"data"))
    assert r.pages[0].source == "text"
    assert render.calls == 0 and vision.calls == 0  # 비용 0


# ── 🔴 OCR 자격증명 없음(ocr=None) → 1단계→3단계 Vision 경로 ─────────────


def test_ocr_none_falls_through_to_vision():
    render, vision = RenderSpy(), FakeVision("Docker React 배포")
    p = _parser([""], render_page=render, ocr=None, vision=vision, min_chars=50)
    r = _run(p.parse(b"data"))
    assert r.pages[0].source == "vision" and "Docker" in r.text
    assert render.calls == 1 and vision.calls == 1


# ── 2단계 OCR 사용/스킵 판정 ────────────────────────────────────────────


def test_ocr_sufficient_does_not_call_vision():
    ocr, vision = FakeOcr(OcrResult("x" * 100, 0.9)), FakeVision("kw")
    p = _parser([""], render_page=RenderSpy(), ocr=ocr, vision=vision, min_chars=50, ocr_conf_min=0.6)
    r = _run(p.parse(b"data"))
    assert r.pages[0].source == "ocr" and ocr.calls == 1 and vision.calls == 0


def test_ocr_low_confidence_falls_to_vision():
    ocr, vision = FakeOcr(OcrResult("x" * 100, 0.3)), FakeVision("kw")
    p = _parser([""], render_page=RenderSpy(), ocr=ocr, vision=vision, min_chars=50, ocr_conf_min=0.6)
    r = _run(p.parse(b"data"))
    assert r.pages[0].source == "vision" and vision.calls == 1


# ── 4단계 폴백 + 상한 + 손상 방어 ──────────────────────────────────────


def test_all_insufficient_no_vision_is_none():
    p = _parser([""], render_page=RenderSpy(), ocr=None, vision=None, min_chars=50)
    r = _run(p.parse(b"data"))
    assert r.pages[0].source == "none" and r.text == "" and not r.has_text


def test_max_pages_limit():
    p = _parser([""] * 10, render_page=RenderSpy(), vision=FakeVision("k"), min_chars=50, max_pages=3)
    r = _run(p.parse(b"data"))
    assert len(r.pages) == 3


def test_extract_failure_returns_empty_result():
    def boom(_d):
        raise ValueError("corrupt pdf")

    p = DocumentParser(extract_page_texts=boom, render_page=RenderSpy())
    r = _run(p.parse(b"data"))
    assert r.text == "" and r.pages == []


def test_render_failure_yields_none_page():
    def boom(_d, _i):
        raise RuntimeError("render fail")

    p = _parser([""], render_page=boom, vision=FakeVision("k"), min_chars=50)
    r = _run(p.parse(b"data"))
    assert r.pages[0].source == "none"


# ── DocumentSource: S3 + PDF/이미지 분기 ───────────────────────────────


class FakeS3:
    def __init__(self, mapping):
        self._mapping = mapping

    async def fetch(self, key, max_bytes):
        return self._mapping.get(key)


def test_docsource_missing_file_returns_empty():
    ds = DocumentSource(FakeS3({}))
    assert _run(ds.fetch_and_parse("missing")) == ""


def test_docsource_non_string_key_returns_empty():
    ds = DocumentSource(FakeS3({}))
    assert _run(ds.fetch_and_parse(None)) == ""


def test_docsource_pdf_extracts_text(monkeypatch):
    import app.competency.document as doc

    monkeypatch.setattr(doc, "pdf_page_texts", lambda _data: ["React로 대시보드를 구현했다. " * 4])
    ds = DocumentSource(FakeS3({"k": b"%PDF-1.4 dummy"}))
    text = _run(ds.fetch_and_parse("k"))
    assert text.startswith("[업로드 문서]") and "React로 대시보드를 구현했다" in text


def test_docsource_image_goes_to_vision(monkeypatch):
    # PDF 아님(이미지) → 텍스트 없음 → Vision. provider 없이 FakeVision 주입.
    ds = DocumentSource(FakeS3({"img": b"\x89PNG..."}), vision=FakeVision("Figma 디자인"))
    text = _run(ds.fetch_and_parse("img"))
    assert "Figma 디자인" in text
