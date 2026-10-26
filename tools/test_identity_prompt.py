"""W-20261026-017: إعادة التعرّف عند أوّل رسالة بعد بدءٍ ملتبس (UserPromptSubmit)، بلا إبطاء للرسائل العاديّة."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import session_identity as si

ROOT_CWD = r"C:\Users\mesue\delivery_manager_work"


def _session(base, name, sid, title, cli=None):
    d = base / "a" / "b"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"local_{name}.json").write_text(
        json.dumps({"sessionId": sid, "cliSessionId": cli or sid, "title": title, "worktreePath": ROOT_CWD}, ensure_ascii=False), encoding="utf-8")


def _hook(sid):
    return json.dumps({"session_id": sid, "cwd": ROOT_CWD})


def test_two_sessions_same_folder_late_cli_id_gets_correct_identity_once(tmp_path):
    sessions = tmp_path / "sessions"
    # عند البدء: الجلستان في المجلّد نفسِه ومعرّفُ الجلسة الجديدة لم يُكتب بعد → التباس
    _session(sessions, "1", "local_1", "0101 · خفيفة", cli="old-1")
    _session(sessions, "2", "local_2", "0104 · الأمان", cli="cli-2")
    assert si.app_title(ROOT_CWD, "new-1", sessions, wait_s=0) == (None, ["0101 · خفيفة", "0104 · الأمان"])
    si.mark_pending("new-1", ROOT_CWD, tmp_path)
    assert (tmp_path / "handover_notes").is_dir()

    resolver = lambda cwd, sid: si.app_title(cwd, sid, sessions, wait_s=0, pending=set())  # noqa: E731
    assert si.prompt_identity(_hook("new-1"), tmp_path, resolver) == []  # ما زال ملتبساً: تبقى العلامة، لا حقن
    _session(sessions, "1", "local_1", "0101 · خفيفة", cli="new-1")  # كُتب cliSessionId بعد الخطّاف
    lines = si.prompt_identity(_hook("new-1"), tmp_path, resolver)
    assert lines and "0101" in lines[1] and "كان بدؤك ملتبساً" in lines[0]
    assert si.prompt_identity(_hook("new-1"), tmp_path, resolver) == []  # مرّةً واحدة: العلامةُ حُذفت


def test_no_marker_means_no_work_and_no_output(tmp_path):
    calls = []
    assert si.prompt_identity(_hook("plain"), tmp_path, lambda c, s: calls.append(1)) == [] and calls == []
    assert si.prompt_identity("not json", tmp_path) == [] and si.prompt_identity("{}", tmp_path) == []


def test_expired_marker_is_dropped_without_injection(tmp_path):
    si.mark_pending("old", ROOT_CWD, tmp_path, now=datetime.now() - timedelta(seconds=si.PENDING_TTL_S + 5))
    assert si.prompt_identity(_hook("old"), tmp_path, lambda c, s: ("0101 · خفيفة", [])) == []
    assert not si._pending_path("old", tmp_path).exists()


def test_mark_pending_ignores_empty_session_id_and_sanitises_name(tmp_path):
    si.mark_pending("", ROOT_CWD, tmp_path)
    assert not (tmp_path / "handover_notes").exists()
    assert si._pending_path("a/b:c", tmp_path).name == "identity_pending_a_b_c.json"


def test_main_marks_pending_on_ambiguous_root_folder_start(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(si, "ROOT", tmp_path)
    monkeypatch.setattr(si, "app_title", lambda cwd, sid="", base=None, **k: (None, ["0101 · خفيفة", "0104 · الأمان"]))
    monkeypatch.setattr(si, "directory_lines", lambda num=None: [])
    monkeypatch.setattr("sys.argv", ["session_identity.py"])
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(_hook("S1")))
    si.main()
    assert "اسأل 0101" in capsys.readouterr().out and si._pending_path("S1", tmp_path).is_file()


def test_main_prompt_flag_injects_after_late_id(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(si, "ROOT", tmp_path)
    si.mark_pending("S2", ROOT_CWD, tmp_path)
    monkeypatch.setattr(si, "app_title", lambda cwd, sid="", base=None, **k: ("0104 · الأمان", []))
    monkeypatch.setattr(si, "directory_lines", lambda num=None: ["[دليل]"])
    monkeypatch.setattr("sys.argv", ["session_identity.py", "--prompt"])
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(_hook("S2")))
    assert si.main() == 0
    out = capsys.readouterr().out
    assert "0104" in out and "[دليل]" in out and not si._pending_path("S2", tmp_path).exists()
