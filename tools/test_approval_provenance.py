"""مصدرُ الإفادة: «مباشر» أو «نقلاً عن جلسة X» (W-20261016-030)."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import approval_check as ac
import record_owner_confirmation as rc

TOOLS = Path(__file__).resolve().parent
REAL = TOOLS.parent / "owner_confirmations.md"
CARD = "W-20261016-999"


def _file(tmp_path: Path, *rows: str) -> Path:
    f = tmp_path / "owner_confirmations.md"
    f.write_text("".join(rows), encoding="utf-8")
    return f


def _row(session: str, source: str) -> str:
    return rc.row(session, CARD, "ادفع", "", head="abcdef12", source=source)


def _run_record(*extra: str) -> subprocess.CompletedProcess:
    base = [sys.executable, str(TOOLS / "record_owner_confirmation.py"), "--session", "0403", "--target", CARD, "--quote", "ادفع", "--head", "abcdef12"]
    return subprocess.run(base + list(extra), capture_output=True, text=True, encoding="utf-8")


def test_recording_without_source_is_rejected():
    r = _run_record()
    assert r.returncode != 0 and "--source" in r.stderr


def test_recording_with_invalid_source_is_rejected():
    assert _run_record("--source", "سمعتُ").returncode != 0


def test_valid_sources_are_normalized():
    assert rc.normalize_source("مباشر") == "مباشر"
    assert rc.normalize_source("نقلاً عن جلسة 0101") == "نقلاً عن 0101"
    assert rc.normalize_source("نقلاً عن 0101") == "نقلاً عن 0101"
    assert rc.normalize_source("نقلاً عن جلسة") is None


def test_row_keeps_column_count_with_source():
    assert _row("0403", "مباشر").count("|") == rc.row("0403", CARD, "ادفع", "", head="abcdef12").count("|")
    assert "(إفادةُ جلسة) مصدره: نقلاً عن 0101 |" in _row("0501", "نقلاً عن 0101")


def test_relayed_without_direct_from_hearer_is_rejected_when_enforced(tmp_path):
    f = _file(tmp_path, _row("0501", "نقلاً عن 0101"))
    ev = ac.confirmations_evidence(CARD, "abcdef12", enforce=True, path=f)
    assert [st for _, st in ev] == ["unverified"]


def test_relayed_with_direct_from_hearer_is_accepted(tmp_path):
    f = _file(tmp_path, _row("0101", "مباشر"), _row("0501", "نقلاً عن 0101"))
    ev = ac.confirmations_evidence(CARD, "abcdef12", enforce=True, path=f)
    assert [st for _, st in ev] == ["ok", "ok"]


def test_warning_mode_prints_but_does_not_reject(tmp_path):
    f = _file(tmp_path, _row("0501", "نقلاً عن 0101"))
    ev = ac.confirmations_evidence(CARD, "abcdef12", enforce=False, path=f)
    assert [st for _, st in ev] == ["ok"] and "إنذار" in ev[0][0]


def test_direct_from_another_target_does_not_count(tmp_path):
    other = rc.row("0101", "W-20261016-998", "ادفع", "", head="abcdef12", source="مباشر")
    f = _file(tmp_path, other, _row("0501", "نقلاً عن 0101"))
    ev = ac.confirmations_evidence(CARD, "abcdef12", enforce=True, path=f)
    assert [st for _, st in ev] == ["unverified"]


def test_every_existing_line_is_still_accepted(tmp_path):
    copy = tmp_path / "owner_confirmations.md"
    shutil.copy(REAL, copy)
    text = copy.read_text(encoding="utf-8")
    checked = 0
    for ln in text.splitlines():
        if not ln.startswith("|") or "ملغى[" in ln or ac.SOURCE_IN_LINE.search(ln):
            continue
        m = re.search(r"W-\d{8}-\d{3}|#\d+", ln)
        if not m:
            continue
        assert line_kind(ln) == "legacy"
        ev = ac.confirmations_evidence(m.group(0), None, enforce=True, path=copy)
        assert ev and not any(st == "unverified" for _, st in ev), ln
        checked += 1
    assert checked > 0


def line_kind(ln: str) -> str:
    return ac.line_source(ln)[0]
