"""اختبارات حارس فهرس الذاكرة (W-20261013-030)."""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import memory_index_guard as g  # noqa: E402

IDX = r"C:\Users\mesue\.claude\projects\D--shschool-mvp\memory\MEMORY.md"
WT = "D:/shschool_mvp/.claude/worktrees/"


def _names(tmp_path, monkeypatch, mapping):
    f = tmp_path / "names.json"
    f.write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(g, "NAMES", f)


def _p(tool, tree, **tool_in):
    return {"tool_name": tool, "tool_input": tool_in, "cwd": WT + tree, "session_id": "abcd1234"}


def test_other_session_is_warned_then_blocked_on_edit_write_bash(tmp_path, monkeypatch):
    _names(tmp_path, monkeypatch, {"t-0501": "0501 · المعاينة", "t-0103": "0103 · الحوكمة"})
    monkeypatch.delenv("MEMORY_INDEX_GUARD_MODE", raising=False)
    monkeypatch.setattr(g, "MODE_FILE", tmp_path / "none.mode")
    for payload in (
        _p("Edit", "t-0501", file_path=IDX),
        _p("Write", "t-0501", file_path=IDX.replace("\\", "/")),
        _p("Bash", "t-0501", command=f"echo '- x' >> '{IDX}'"),
        _p("Bash", "t-0501", command=f"sed -i 's/a/b/' {IDX}"),
    ):
        assert g.decide(payload)[0] == "warn"
    monkeypatch.setenv("MEMORY_INDEX_GUARD_MODE", "block")
    verdict, msg = g.decide(_p("Edit", "t-0501", file_path=IDX))
    assert verdict == "deny" and "on_demand" in msg and "0103" in msg


def test_0103_and_reads_and_other_files_pass(tmp_path, monkeypatch):
    _names(tmp_path, monkeypatch, {"t-0501": "0501 · المعاينة", "t-0103": "0103 · الحوكمة"})
    monkeypatch.setenv("MEMORY_INDEX_GUARD_MODE", "block")
    assert g.decide(_p("Edit", "t-0103", file_path=IDX))[0] == "allow"
    assert g.decide(_p("Bash", "t-0501", command=f"cat {IDX}"))[0] == "allow"
    assert g.decide(_p("Bash", "t-0501", command=f"grep -c x {IDX}"))[0] == "allow"
    on_demand = IDX.replace("MEMORY.md", "on_demand\feedback_x.md")
    assert g.decide(_p("Write", "t-0501", file_path=on_demand))[0] == "allow"
    assert g.decide(_p("Write", "t-0501", file_path=on_demand.replace("on_demand\feedback_x", "INDEX_violations_pending")))[0] == "allow"


def test_any_fault_is_allow_and_unknown_sessions_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(g, "NAMES", tmp_path / "missing.json")
    monkeypatch.setenv("MEMORY_INDEX_GUARD_MODE", "block")
    assert g.decide(_p("Edit", "unknown-tree", file_path=IDX))[0] == "allow"
    here = Path(__file__).parent / "memory_index_guard.py"
    out = subprocess.run([sys.executable, str(here)], input="not json", capture_output=True, text=True)
    assert out.returncode == 0 and out.stdout == ""
