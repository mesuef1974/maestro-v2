from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "prepush_image"))
import git_open_prs as g  # noqa: E402


def _cp(out="", rc=0):
    return subprocess.CompletedProcess([], rc, stdout=out, stderr="")


def _fake(refs, merged=(), files=None, rc_refs=0):
    files = files or {}

    def run(cmd):
        if cmd[1] == "for-each-ref":
            return _cp(refs, rc_refs)
        if cmd[1] == "merge-base" and cmd[2] == "--is-ancestor":
            return _cp("", 0 if cmd[3] in merged else 1)
        if cmd[1] == "merge-base":
            return _cp("base1\n")
        if cmd[1] == "diff":
            return _cp("\n".join(files.get(cmd[-1], [])))
        raise AssertionError(cmd)

    return run


def test_open_branches_exclude_main_head_and_merged():
    refs = "origin/HEAD aaa\norigin/main bbb\norigin/claude/a ccc\norigin/claude/old ddd\norigin\n"
    out = g.open_pull_requests(_fake(refs, merged={"ddd"}, files={"ccc": ["app/migrations/0007_x.py"]}))
    assert list(out) == ["claude/a (فرع بعيد)"]
    assert out["claude/a (فرع بعيد)"] == {"head": "ccc", "branch": "claude/a", "files": ["app/migrations/0007_x.py"]}


def test_unreadable_refs_raise_not_measured():
    class NM(Exception):
        pass

    try:
        g.open_pull_requests(_fake("", rc_refs=128), not_measured=NM)
    except NM:
        return
    raise AssertionError("كان يجب أن يرفع not_measured")


def test_check_maps_status_and_restores_env(monkeypatch):
    class PC:
        OK, FAIL, MISSING = "ok", "fail", "missing"

    class CMC:
        OK, COLLISION, MISSING = 0, 1, 3
        NotMeasuredError = RuntimeError
        open_pull_requests = None

        @staticmethod
        def _run(cmd):
            return _cp()

        @staticmethod
        def run():
            assert CMC.open_pull_requests() == {}
            return 1, "تصادم: x"

    monkeypatch.setenv("PREPUSH_GIT_DIR", "/gitmain")
    monkeypatch.delenv("GIT_DIR", raising=False)
    assert g.check(PC, CMC) == ("fail", "تصادم: x")
    import os

    assert "GIT_DIR" not in os.environ
