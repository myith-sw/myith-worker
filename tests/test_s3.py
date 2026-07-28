"""S3Fetcher 테스트 — 실패·상한이 None으로 degrade하는지(C-3). boto3 없이 가짜 클라이언트."""

import asyncio

from app.storage.s3 import S3Fetcher


def _run(coro):
    return asyncio.run(coro)


class _Body:
    def __init__(self, data=b"", *, raises=None):
        self._data, self._raises = data, raises
        self.closed = False

    def read(self, n):
        if self._raises:
            raise self._raises
        return self._data[:n]

    def close(self):
        self.closed = True


class _FakeClient:
    def __init__(self, *, obj=None, get_raises=None):
        self._obj, self._get_raises = obj, get_raises

    def get_object(self, Bucket, Key):
        if self._get_raises:
            raise self._get_raises
        return self._obj


def test_fetch_ok_returns_bytes():
    body = _Body(b"%PDF-1.4 data")
    client = _FakeClient(obj={"ContentLength": 12, "Body": body})
    assert _run(S3Fetcher(bucket="b", client=client).fetch("k", 1000)) == b"%PDF-1.4 data"
    assert body.closed  # 스트림 닫힘


def test_get_object_failure_returns_none():
    client = _FakeClient(get_raises=RuntimeError("403 AccessDenied"))
    assert _run(S3Fetcher(bucket="b", client=client).fetch("k", 1000)) is None


def test_midstream_read_failure_returns_none():
    # 🔴 스트림 중간 실패도 None으로 degrade해야 한다(리뷰 high 수정)
    body = _Body(raises=RuntimeError("IncompleteRead / ReadTimeout"))
    client = _FakeClient(obj={"ContentLength": 100, "Body": body})
    assert _run(S3Fetcher(bucket="b", client=client).fetch("k", 1000)) is None


def test_oversize_by_content_length_returns_none():
    client = _FakeClient(obj={"ContentLength": 99999, "Body": _Body(b"x")})
    assert _run(S3Fetcher(bucket="b", client=client).fetch("k", 10)) is None


def test_oversize_by_stream_returns_none():
    # ContentLength가 없어도 실제 스트림이 상한 초과면 스킵
    client = _FakeClient(obj={"Body": _Body(b"x" * 50)})
    assert _run(S3Fetcher(bucket="b", client=client).fetch("k", 10)) is None


def test_no_bucket_returns_none():
    assert _run(S3Fetcher(bucket=None, client=_FakeClient()).fetch("k", 10)) is None
