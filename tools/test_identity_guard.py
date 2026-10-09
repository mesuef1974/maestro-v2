"""اختباراتُ حارس الهويّة (W-20261009-008) — مستودعٌ تجريبيٌّ صغير باسمٍ يحوي shschool_mvp.

شجرةٌ بلا الترقية تُمنع، والمرقّاةُ بإيصال تمرّ، وملفٌّ غيرُ واجهةٍ يمرّ، وإيصالٌ قديمٌ يُمنع، وغيابُ git لا يُسقط.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import identity_ack as ack  # noqa: E402
import identity_guard as g  # noqa: E402

CHECK = g.CHECKLIST


def run(cwd: Path, *a: str) -> str:
    r = subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, encoding="utf-8", check=True)
    return r.stdout.strip()


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    """مستودعٌ: إيداع قديم A، ثمّ إيداع الترقية U (يضيف ملفّ 95)، ثمّ فرعٌ قديم من A."""
    top = tmp_path / "shschool_mvp"
    top.mkdir()
    run(top, "init", "-q", "-b", "main")
    run(top, "config", "user.email", "t@t")
    run(top, "config", "user.name", "t")
    (top / "README.md").write_text("a", encoding="utf-8")
    run(top, "add", "README.md")
    run(top, "commit", "-qm", "A")
    old = run(top, "rev-parse", "HEAD")
    (top / CHECK).parent.mkdir(parents=True)
    (top / CHECK).write_text("قائمة 95", encoding="utf-8")
    run(top, "add", CHECK)
    run(top, "commit", "-qm", "U")
    upgrade = run(top, "rev-parse", "HEAD")
    monkeypatch.setattr(g, "SKILL_UPGRADE", upgrade)
    (top / "templates").mkdir()
    return top, old


def edit(top: Path, rel: str = "templates/x.html", tool: str = "Edit") -> dict:
    return {"tool_name": tool, "tool_input": {"file_path": str(top / rel)}, "cwd": str(top)}


def test_stale_tree_is_denied(repo):
    top, old = repo
    run(top, "checkout", "-q", old)  # لا ترقية سلفاً
    action, msg = g.decide(edit(top))
    assert action == "deny" and "ادمج main" in msg


def test_upgraded_with_ack_passes(repo, capsys):
    top, _ = repo
    assert g.decide(edit(top))[0] == "deny"  # مرقّاة لكن بلا إيصال
    sys.argv = ["identity_ack.py", "--cwd", str(top)]
    assert ack.main() == 0
    assert g.decide(edit(top)) is None
    assert g.decide(edit(top, tool="Write", rel="static/css/custom/20-components.css")) is None


def test_non_ui_file_passes_even_if_stale(repo):
    top, old = repo
    run(top, "checkout", "-q", old)
    assert g.decide(edit(top, rel="core/views.py")) is None
    assert g.decide(edit(top, rel="docs/readme.md")) is None


def test_changed_checklist_invalidates_ack(repo):
    top, _ = repo
    sys.argv = ["identity_ack.py", "--cwd", str(top)]
    ack.main()
    assert g.decide(edit(top)) is None
    (top / CHECK).write_text("قائمة 95 معدّلة", encoding="utf-8")
    assert g.decide(edit(top))[0] == "deny"


def test_outside_platform_tree_passes(tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    run(other, "init", "-q")
    payload = {"tool_name": "Edit", "tool_input": {"file_path": str(other / "templates" / "x.html")}, "cwd": str(other)}
    assert g.decide(payload) is None


def test_no_git_never_drops_session(tmp_path):
    folder = tmp_path / "shschool_mvp_nogit"
    (folder / "templates").mkdir(parents=True)
    payload = {"tool_name": "Edit", "tool_input": {"file_path": str(folder / "templates" / "x.html")}, "cwd": str(folder)}
    assert g.decide(payload) is None  # لا مستودع: لا شجرة منصّة فيمرّ بصمت


def test_git_commit_with_staged_ui_in_stale_tree(repo):
    top, old = repo
    run(top, "checkout", "-q", old)
    (top / "templates" / "x.html").write_text("x", encoding="utf-8")
    run(top, "add", "templates/x.html")
    payload = {"tool_name": "Bash", "tool_input": {"command": 'git commit -m "x"'}, "cwd": str(top)}
    assert g.decide(payload)[0] == "deny"
    run(top, "reset", "-q")
    assert g.decide(payload) is None  # لا ملفَّ واجهة في الفهرس
    other = {"tool_name": "Bash", "tool_input": {"command": "ls templates"}, "cwd": str(top)}
    assert g.decide(other) is None


def test_warn_mode_never_denies(repo, monkeypatch, capsys):
    top, old = repo
    run(top, "checkout", "-q", old)
    monkeypatch.setenv("IDENTITY_GUARD_MODE", "warn")
    g.emit(*g.decide(edit(top)), g.mode())
    out = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert "permissionDecision" not in out and "additionalContext" in out
    monkeypatch.setenv("IDENTITY_GUARD_MODE", "block")
    g.emit(*g.decide(edit(top)), g.mode())
    out = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"


def test_main_survives_garbage_input(monkeypatch):
    import io

    monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
    assert g.main() == 0


def test_speed_under_half_second(repo):
    import time

    top, old = repo
    run(top, "checkout", "-q", old)
    t = time.perf_counter()
    g.decide(edit(top))
    assert time.perf_counter() - t < 0.5
