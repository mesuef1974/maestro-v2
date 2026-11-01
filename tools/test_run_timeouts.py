"""W-20261101-002: تعليقُ gh/git لا يعلّق دورةَ المضخّة — مهلةٌ في approval_check.run وvisual_gate.head8."""
import subprocess

import approval_check as ac
import pytest
import visual_gate as vg


def _hang(*a, **k):
    raise subprocess.TimeoutExpired(a[0], k.get("timeout", 0))


def test_approval_check_run_returns_124_on_timeout_instead_of_hanging(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _hang)
    rc, out = ac.run(["gh", "pr", "list"])
    assert rc == 124 and "انتهت المهلة" in out


def test_approval_check_passes_a_timeout_to_subprocess(monkeypatch):
    seen = {}

    def fake(cmd, **k):
        seen.update(k)
        return subprocess.CompletedProcess(cmd, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake)
    assert ac.run(["x"]) == (0, "ok") and seen["timeout"] == ac.RUN_TIMEOUT_S


def test_visual_gate_head8_exits_cleanly_on_timeout(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _hang)
    with pytest.raises(SystemExit, match="مهلة"):
        vg.head8(".")
