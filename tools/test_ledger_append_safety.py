"""سلامةُ إلحاق الدفتر (الموجة 0.4، D-453م): قفلٌ بين العمليّات، fsync، ونسخةٌ احتياطيّةٌ يوميّة قابلةٌ للاستعادة."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

import ledger

TOOLS = Path(__file__).resolve().parent

WRITER = """
import sys
sys.path.insert(0, {tools!r})
import ledger
tag, n, path = sys.argv[1], int(sys.argv[2]), sys.argv[3]
for i in range(n):
    ledger.append_event("note", tag, {{"i": i, "pad": "x" * 6000}}, path=path)
"""


def test_two_processes_appending_concurrently_lose_and_corrupt_nothing(tmp_path):
    path = tmp_path / "events.jsonl"
    code = WRITER.format(tools=str(TOOLS))
    n = 150
    procs = [subprocess.Popen([sys.executable, "-c", code, tag, str(n), str(path)]) for tag in ("A", "B", "C", "D")]
    assert [p.wait(timeout=120) for p in procs] == [0, 0, 0, 0]
    lines = path.read_text(encoding="utf-8").splitlines()
    events = [json.loads(ln) for ln in lines]  # أيُّ سطرٍ ملتحمٍ أو مبتور يُسقط هذا
    assert len(events) == 4 * n
    for tag in "ABCD":
        assert sorted(e["data"]["i"] for e in events if e["id"] == tag) == list(range(n))


def test_append_is_fsynced(tmp_path):
    with mock.patch.object(os, "fsync", wraps=os.fsync) as fs:
        ledger.append_event("note", "W-1", {"x": 1}, path=tmp_path / "events.jsonl")
    assert fs.called


def test_lock_times_out_with_a_clear_error_when_held(tmp_path):
    path = tmp_path / "events.jsonl"
    with ledger._file_lock(path):
        # النافذةُ القصيرةُ تكفي لإثبات أنّ القفلَ ممسوكٌ فعلاً عبر واصفٍ آخر
        with pytest.raises(ledger.LedgerError, match="قفل"):
            with ledger._file_lock(path, timeout=0.2):
                pass
    with ledger._file_lock(path, timeout=0.2):  # وبعد الإفراج يُؤخذ
        pass


def test_a_torn_last_line_does_not_merge_with_the_next_event(tmp_path):
    path = tmp_path / "events.jsonl"
    ledger.append_event("note", "W-1", {"a": 1}, path=path)
    with path.open("ab") as fh:
        fh.write(b'{"ts": "t", "id": "W-2", "ki')  # انقطاعٌ في منتصف سطر
    ledger.append_event("note", "W-3", {"b": 2}, path=path)
    ok = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        try:
            ok.append(json.loads(ln)["id"])
        except json.JSONDecodeError:
            pass
    assert ok == ["W-1", "W-3"]


def test_daily_backup_is_taken_once_before_the_first_append_of_the_day_and_restores(tmp_path):
    path = tmp_path / "events.jsonl"
    ledger.append_event("note", "W-1", {}, path=path)
    assert not (tmp_path / "backups").exists()  # دفترٌ فارغٌ لا يُنسخ
    before = path.read_bytes()
    with mock.patch.object(ledger, "datetime") as dt:
        dt.now.return_value.strftime.return_value = "2026-10-21"
        dt.now.return_value.isoformat.return_value = "2026-10-21T10:00:00+03:00"
        ledger.append_event("note", "W-2", {}, path=path)
        ledger.append_event("note", "W-3", {}, path=path)
    backups = sorted((tmp_path / "backups").glob("events-*.jsonl"))
    assert [b.name for b in backups] == ["events-2026-10-21.jsonl"]
    assert backups[0].read_bytes() == before  # صورةُ الدفتر قبل أوّل إلحاق اليوم، لا بعده
    assert len(path.read_text(encoding="utf-8").splitlines()) == 3
    path.write_bytes(backups[0].read_bytes())  # الاستعادة: نسخٌ مباشر
    assert [e["id"] for e in ledger.load_events(path)] == ["W-1"]


def test_old_backups_are_pruned(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text('{"ts": "t", "id": "W-1", "kind": "note", "data": {}}\n', encoding="utf-8")
    bdir = tmp_path / "backups"
    bdir.mkdir()
    for d in range(1, 41):
        (bdir / f"events-2026-09-{d:02d}.jsonl").write_text("x")
    ledger.daily_backup(path, today="2026-10-21")
    names = sorted(b.name for b in bdir.glob("events-*.jsonl"))
    assert len(names) == ledger.BACKUP_KEEP and names[-1] == "events-2026-10-21.jsonl"
