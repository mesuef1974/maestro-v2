from __future__ import annotations

from pathlib import Path

import baseline_refresh as b


def _fake(monkeypatch, outputs):
    calls = []

    def fake_run(cmd, cwd):
        calls.append(cmd)
        return outputs.pop(0)

    monkeypatch.setattr(b, "run", fake_run)
    return calls


def test_a_worse_line_is_refused_and_nothing_is_updated(monkeypatch):
    calls = _fake(monkeypatch, [(1, "WORSE a.py: 100 → 400\nSTALE b.py: 900 → 800\n")])
    code, msg = b.ratchet(Path("."), "tests.file_size_ratchet", True, "حجم")
    assert code == b.WORSE and "تُرفض" in msg and len(calls) == 1  # لم يُستدعَ --update


def test_only_stale_lines_trigger_the_update(monkeypatch):
    calls = _fake(monkeypatch, [(0, "STALE b.py: 900 → 800\n"), (0, "سُجّل\n")])
    code, msg = b.ratchet(Path("."), "tests.file_size_ratchet", True, "حجم")
    assert code == b.OK and "سُجّل 1" in msg and "--update" in calls[1]


def test_check_mode_never_writes(monkeypatch):
    calls = _fake(monkeypatch, [(0, "STALE b.py: 900 → 800\n")])
    code, msg = b.ratchet(Path("."), "tests.file_size_ratchet", False, "حجم")
    assert code == b.OK and len(calls) == 1 and "بلا --check" in msg


def test_nothing_to_record(monkeypatch):
    _fake(monkeypatch, [(0, "mypy: 5 خطأً في 2 ملفّاً\n")])
    code, msg = b.ratchet(Path("."), "tests.mypy_ratchet", True, "mypy")
    assert code == b.OK and "لا نقصَ" in msg


def test_mypy_version_skew_refusal_is_reported_not_hidden(monkeypatch):
    _fake(monkeypatch, [(1, "نقص ولم يُسجَّل (…): a.py: 9 → 3\n"), (2, "رُفض --update: إصداراتُ الفاحص\n")])
    code, msg = b.ratchet(Path("."), "tests.mypy_ratchet", True, "mypy")
    assert code == b.UNMEASURED and "رفض الأمرُ نفسُه" in msg


def test_a_tool_that_could_not_run_is_unmeasured_not_ok(monkeypatch):
    _fake(monkeypatch, [(127, "No module named tests.mypy_ratchet\n")])
    code, _msg = b.ratchet(Path("."), "tests.mypy_ratchet", True, "mypy")
    assert code == b.UNMEASURED


def test_secret_keys_ignore_line_numbers():
    base = {"results": {"a.py": [{"hashed_secret": "h1", "line_number": 3}, {"hashed_secret": "h2", "line_number": 9}]}}
    moved = {"results": {"a.py": [{"hashed_secret": "h1", "line_number": 40}, {"hashed_secret": "h2", "line_number": 2}]}}
    assert b.secret_keys(base) == b.secret_keys(moved) == {("a.py", "h1"), ("a.py", "h2")}
