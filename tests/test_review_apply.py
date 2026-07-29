"""화면 텍스트 검수 재입력 (review_apply). CSV 파싱 + 오버라이드 라운드트립 + revert."""

import csv
import json
from pathlib import Path

import pytest

from app.seed import overrides
from app.seed.review_apply import main, read_cert_hidden, read_taglines


def _write_csv(path: Path, cols: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


# ── CSV 파싱 규칙 ────────────────────────────────────────────────────────


def test_read_taglines_skips_empty_new(tmp_path):
    p = tmp_path / "t.csv"
    _write_csv(p, ["job_code", "tagline_new"], [
        {"job_code": "backend", "tagline_new": "새 소개"},
        {"job_code": "frontend", "tagline_new": ""},  # 비면 건드리지 않음
        {"job_code": "hr", "tagline_new": "  "},  # 공백도 스킵
    ])
    assert read_taglines(p) == {"backend": "새 소개"}


def test_read_cert_hidden_only_hide_rows(tmp_path):
    p = tmp_path / "c.csv"
    _write_csv(p, ["ncs_unit_code", "cert_code", "action"], [
        {"ncs_unit_code": "U1", "cert_code": "A", "action": "HIDE"},
        {"ncs_unit_code": "U1", "cert_code": "B", "action": "KEEP"},  # KEEP 제외
        {"ncs_unit_code": "U2", "cert_code": "C", "action": "hide"},  # 대소문자 무시
    ])
    assert read_cert_hidden(p) == [["U1", "A"], ["U2", "C"]]  # 정렬·중복제거


# ── 라운드트립: review_apply → overrides 읽기 ────────────────────────────


def test_apply_writes_overrides_loaders_read_them(tmp_path, monkeypatch):
    tag = tmp_path / "t.csv"
    cert = tmp_path / "c.csv"
    _write_csv(tag, ["job_code", "tagline_new"], [{"job_code": "backend", "tagline_new": "심장을 만든다"}])
    _write_csv(cert, ["ncs_unit_code", "cert_code", "action"], [{"ncs_unit_code": "U1", "cert_code": "A", "action": "HIDE"}])

    tfile = tmp_path / "tagline_overrides.json"
    cfile = tmp_path / "cert_hidden.json"
    monkeypatch.setattr(overrides, "OVERRIDES_DIR", tmp_path)
    monkeypatch.setattr(overrides, "TAGLINE_FILE", tfile)
    monkeypatch.setattr(overrides, "CERT_HIDDEN_FILE", cfile)

    import app.seed.review_apply as ra
    monkeypatch.setattr(ra, "OVERRIDES_DIR", tmp_path)
    monkeypatch.setattr(ra, "TAGLINE_FILE", tfile)
    monkeypatch.setattr(ra, "CERT_HIDDEN_FILE", cfile)

    rc = main(["--taglines", str(tag), "--certs", str(cert)])
    assert rc == 0
    assert overrides.load_tagline_overrides(tfile) == {"backend": "심장을 만든다"}
    assert overrides.load_cert_hidden(cfile) == {("U1", "A")}


def test_dry_run_does_not_write(tmp_path, monkeypatch):
    tag = tmp_path / "t.csv"
    _write_csv(tag, ["job_code", "tagline_new"], [{"job_code": "backend", "tagline_new": "x"}])
    tfile = tmp_path / "tagline_overrides.json"
    import app.seed.review_apply as ra
    monkeypatch.setattr(ra, "TAGLINE_FILE", tfile)
    monkeypatch.setattr(ra, "OVERRIDES_DIR", tmp_path)
    main(["--taglines", str(tag), "--dry-run"])
    assert not tfile.exists()  # dry-run은 파일 미생성


def test_revert_empties_overrides(tmp_path, monkeypatch):
    tfile = tmp_path / "tagline_overrides.json"
    cfile = tmp_path / "cert_hidden.json"
    tfile.write_text('{"backend": "old"}', encoding="utf-8")
    cfile.write_text('[["U1", "A"]]', encoding="utf-8")
    import app.seed.review_apply as ra
    monkeypatch.setattr(ra, "OVERRIDES_DIR", tmp_path)
    monkeypatch.setattr(ra, "TAGLINE_FILE", tfile)
    monkeypatch.setattr(ra, "CERT_HIDDEN_FILE", cfile)
    main(["--revert"])
    assert json.loads(tfile.read_text()) == {}
    assert json.loads(cfile.read_text()) == []


# ── overrides 읽기: 부재/빈 파일 안전 ────────────────────────────────────


def test_load_overrides_absent_safe(tmp_path):
    assert overrides.load_tagline_overrides(tmp_path / "nope.json") == {}
    assert overrides.load_cert_hidden(tmp_path / "nope.json") == set()


def test_load_tagline_overrides_drops_blank_values(tmp_path):
    p = tmp_path / "t.json"
    p.write_text('{"backend": "x", "frontend": ""}', encoding="utf-8")
    assert overrides.load_tagline_overrides(p) == {"backend": "x"}
