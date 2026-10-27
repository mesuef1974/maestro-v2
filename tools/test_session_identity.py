from __future__ import annotations

import json

import session_identity as si

NAMES = {"amazing-x-1": "0601 · الإصدار: الدمجُ والنشر", "fast-y-2": "0404 · إدارة: شحنٌ ودمجٌ آليّان (W-015)"}


def test_tree_name_from_windows_path():
    assert si.tree_name(r"D:\shschool_mvp\.claude\worktrees\amazing-x-1") == "amazing-x-1"
    assert si.tree_name(r"D:\shschool_mvp\.claude\worktrees\amazing-x-1\tools") == "amazing-x-1"
    assert si.tree_name(r"D:\shschool_mvp") is None
    assert si.tree_name(r"C:\other\worktrees\z") is None


def test_permanent_session_gets_its_card_and_no_flexible_assumption():
    t = si.lookup(r"D:\shschool_mvp\.claude\worktrees\amazing-x-1", NAMES)
    msg = si.message(t, "amazing-x-1")
    assert "0601" in msg and "role_cards/0601.md" in msg and "my_state.py 0601" in msg
    assert "لا تفترض أنّك مرنة" in msg


def test_flexible_session_points_to_shared_card():
    t = si.lookup(r"D:\shschool_mvp\.claude\worktrees\fast-y-2", NAMES)
    msg = si.message(t, "fast-y-2")
    assert "role_cards/04.md" in msg and "لا تفترض أنّك مرنة" not in msg


def test_unknown_tree_asks_maestro():
    msg = si.message(None, "who-1")
    assert "0101" in msg and "who-1" in msg


def test_handoff_rule_text_covers_three_states(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["session_identity.py", "--cwd", r"D:\shschool_mvp\.claude\worktrees\amazing-x-1"])
    si.main()
    injected = capsys.readouterr().out
    assert "COMMON.md" in injected and "delivered" not in injected  # W-20261027-002: النصُّ الكامل صار في COMMON.md والحقنُ سطرُ إحالة
    import render_role_cards

    msg = render_role_cards.COMMON_EXTRA
    assert "## المراسلة بين الجلسات" in msg and "[قاعدة المالك] المالكُ في الاعتماد والمعاينة فقط" in msg
    assert "delivered` = مبلّغة" in msg and "queued` = في الطابور فلا تُعاد" in msg
    assert "بعد دقيقتين من list_events" in msg and "مرةً واحدةً" in msg
    assert "undelivered` = لم تبلغ فأعِد الإرسال بعد دقيقة" in msg
    assert "(بلغت / في الطابور / لم تبلغ)" in msg and "ولا تسأل المالكَ عن إعادة الإرسال" in msg


def _session(base, name, sid, title, tree, archived=False, cli=None):
    d = base / "a" / "b"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"local_{name}.json").write_text(
        json.dumps({"sessionId": sid, "cliSessionId": cli or sid, "title": title, "worktreePath": tree, "isArchived": archived}),
        encoding="utf-8",
    )


TREE = r"D:\shschool_mvp\.claude\worktrees\peaceful-1"


def test_live_title_resolves_by_session_id_even_when_two_sessions_share_the_tree(tmp_path):
    _session(tmp_path, "1", "local_1", "0405 · غياب", TREE, cli="cli-1")
    _session(tmp_path, "2", "local_2", "0423 · أعمدة", TREE, cli="cli-2")
    assert si.app_title(TREE, "cli-2", tmp_path) == ("0423 · أعمدة", [])


def test_shared_tree_without_session_id_is_ambiguous_not_guessed(tmp_path):
    _session(tmp_path, "1", "local_1", "0405 · غياب", TREE)
    _session(tmp_path, "2", "local_2", "0423 · أعمدة", TREE)
    assert si.app_title(TREE, "", tmp_path) == (None, ["0405 · غياب", "0423 · أعمدة"])


def test_single_live_session_on_the_tree_wins_over_stale_names(tmp_path):
    _session(tmp_path, "1", "local_1", "0702 · معاون", TREE)
    _session(tmp_path, "2", "local_2", "0101 · قديمة", TREE, archived=True)
    assert si.app_title(TREE + "\tools", "", tmp_path) == ("0702 · معاون", [])


# ── تدرّج الأولويّة عند تكرار المعرّف (W-20261025-008) ──
def _put(base, name, mtime, **kw):
    import os

    d = base / "a" / "b"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"local_{name}.json"
    f.write_text(json.dumps(kw, ensure_ascii=False), encoding="utf-8")
    os.utime(f, (mtime, mtime))


def _run(tmp_path, files, sid="SID-1"):
    for i, (title, kw, m) in enumerate(files):
        _put(tmp_path, str(i), m, title=title, **kw)
    return si.app_title("D:/x", sid, base=tmp_path)


def test_direct_old_beats_newer_prior(tmp_path):
    got = _run(tmp_path, [("0301 قديم", {"cliSessionId": "SID-1"}, 100),
                          ("0405 جديد", {"cliSessionId": "X", "priorCliSessionIds": ["SID-1"]}, 200)])
    assert got == ("0301 قديم", [])


def test_two_direct_newest_wins(tmp_path):
    got = _run(tmp_path, [("0301 قديم", {"sessionId": "SID-1"}, 100), ("0302 جديد", {"cliSessionId": "SID-1"}, 200)])
    assert got == ("0302 جديد", [])


def test_two_prior_newest_wins(tmp_path):
    got = _run(tmp_path, [("0301 قديم", {"priorCliSessionIds": ["SID-1"]}, 100),
                          ("0302 جديد", {"priorCliSessionIds": ["SID-1"]}, 200)])
    assert got == ("0302 جديد", [])


def test_archived_is_skipped(tmp_path):
    got = _run(tmp_path, [("0301 قديم", {"cliSessionId": "SID-1"}, 100),
                          ("0302 جديد", {"cliSessionId": "SID-1", "isArchived": True}, 200)])
    assert got == ("0301 قديم", [])


def test_nested_isarchived_does_not_skip_live_session(tmp_path):
    got = _run(tmp_path, [("0301 حيّة", {"cliSessionId": "SID-1", "meta": {"isArchived": True}}, 100)])
    assert got == ("0301 حيّة", [])


def test_my_state_command_carries_arabic_description_hint():
    """W-20261025-029: lang_guard يرفض Bash بلا وصفٍ عربيّ، فالهويّةُ تأمر بوصفٍ عربيّ مع الأمر."""
    msg = si.message("0601 · الإصدار", "t")
    assert "my_state.py 0601" in msg and "بالعربيّة" in msg


def test_directory_line_limited_to_own_id_and_0101(monkeypatch, capsys):
    """W-20261026-002: سطر [عناوين الجلسات] يقتصر على معرّف الجلسة نفسها و0101، ولغيرهما session_directory.py."""
    import session_directory

    entries = {n: {"id": f"local_{n}"} for n in ("0101", "0108", "0301", "0601", "0701")}
    monkeypatch.setattr(session_directory, "entries", lambda: entries)
    monkeypatch.setattr(si, "app_title", lambda c, sid="", base=None: ("0601 · الإصدار", []))
    monkeypatch.setattr("sys.argv", ["session_identity.py", "--cwd", r"D:\shschool_mvp\.claude\worktrees\amazing-x-1"])
    si.main()
    line = next(x for x in capsys.readouterr().out.splitlines() if x.startswith("[المراسلة بين الجلسات]"))
    assert "0601=local_0601" in line and "0101=local_0101" in line
    assert "0108=" not in line and "0301=" not in line and "session_directory.py" in line


def test_late_cli_session_id_is_found_by_rereading_within_wait(tmp_path):
    """W-20261026-006: التطبيق يكتب cliSessionId بعد SessionStart؛ إعادة القراءة تجده قبل السقوط إلى الشجرة الملتبسة."""
    _session(tmp_path, "1", "local_1", "0101 · خفيفة", TREE, cli="old-1")
    _session(tmp_path, "2", "local_2", "0104 · عاملة", TREE, cli="cli-2")
    sleeps = []

    def sleep(s):
        sleeps.append(s)
        _session(tmp_path, "1", "local_1", "0101 · خفيفة", TREE, cli="new-1")  # يصل المعرّف الجديد أثناء الانتظار

    assert si.app_title(TREE, "new-1", tmp_path, wait_s=3.0, pending=set(), sleep=sleep) == ("0101 · خفيفة", [])
    assert len(sleeps) == 1


def test_unmatched_id_falls_back_after_wait_and_stops_polling(tmp_path):
    _session(tmp_path, "1", "local_1", "0105 · وحيدة", TREE)
    sleeps = []
    assert si.app_title(TREE, "never", tmp_path, wait_s=1.0, pending=set(), sleep=sleeps.append) == ("0105 · وحيدة", [])
    assert len(sleeps) == 2


def test_ambiguity_picks_the_session_with_live_auto_clear_marker(tmp_path):
    """التباس 0101/0104 بعلامة مسحٍ ذاتيّ سارية لـ0101 يطبع هويّة 0101."""
    _session(tmp_path, "1", "local_1", "0101 · خفيفة", TREE)
    _session(tmp_path, "2", "local_2", "0104 · عاملة", TREE)
    assert si.app_title(TREE, "", tmp_path, pending={"0101"}) == ("0101 · خفيفة", [])
    assert si.app_title(TREE, "", tmp_path, pending={"0101", "0104"}) == (None, ["0101 · خفيفة", "0104 · عاملة"])
    assert si.app_title(TREE, "", tmp_path, pending=set()) == (None, ["0101 · خفيفة", "0104 · عاملة"])


def test_auto_clear_nums_ignores_expired_and_corrupt_markers(tmp_path):
    from datetime import datetime, timedelta, timezone

    notes = tmp_path / "handover_notes"
    notes.mkdir()
    now = datetime.now(timezone.utc)
    (notes / "auto_clear_0101.json").write_text(json.dumps({"num": "0101", "created_at": now.isoformat()}), encoding="utf-8")
    (notes / "auto_clear_0104.json").write_text(json.dumps({"num": "0104", "created_at": (now - timedelta(hours=1)).isoformat()}), encoding="utf-8")
    (notes / "auto_clear_0108.json").write_text("{", encoding="utf-8")
    assert si.auto_clear_nums(tmp_path) == {"0101"}


# ===== فرع المجلّد الجذر والأرقام الفرعيّة (منقولةٌ من ec1116d) =====
ROOT_CWD = r"C:\Users\mesue\delivery_manager_work"


def _run_main(monkeypatch, capsys, cwd, result):
    monkeypatch.setattr("sys.argv", ["session_identity.py", "--cwd", cwd])
    monkeypatch.setattr(si, "app_title", lambda c, sid="", base=None: result)
    monkeypatch.setattr(si, "directory_lines", lambda num=None: ["[دليل]"])
    si.main()
    return capsys.readouterr().out


def test_root_folder_session_gets_identity_from_live_title(monkeypatch, capsys):
    out = _run_main(monkeypatch, capsys, ROOT_CWD, ("0108 · الجامع", []))
    assert "0108" in out and "[دليل]" in out


def test_root_folder_sub_session_number_is_accepted(monkeypatch, capsys):
    out = _run_main(monkeypatch, capsys, ROOT_CWD, ("0101-أ · فرعيّة", []))
    assert "0101" in out and "[دليل]" in out


def test_root_folder_worktree_cwd_is_still_root_branch(monkeypatch, capsys):
    out = _run_main(monkeypatch, capsys, ROOT_CWD + r"\tools", ("0109 · س", []))
    assert "0109" in out


def test_root_folder_ambiguity_asks_0101(monkeypatch, capsys):
    out = _run_main(monkeypatch, capsys, ROOT_CWD, (None, ["0104 · أ", "0108 · ب"]))
    assert "اسأل 0101" in out and "0104 · أ" in out


def test_root_folder_without_live_title_stays_silent(monkeypatch, capsys):
    assert _run_main(monkeypatch, capsys, ROOT_CWD, (None, [])) == ""


def test_longest_tree_wins_when_nested_entries_match(tmp_path):
    _session(tmp_path, "1", "local_1", "0101 · خفيفة", r"C:\Users\mesue\delivery_manager_work")
    _session(tmp_path, "2", "local_2", "0420 · فرعيّة", r"C:\Users\mesue\delivery_manager_work\sub\deep")
    title, _ = si.app_title(r"C:\Users\mesue\delivery_manager_work\sub\deep\x", "", tmp_path)
    assert title == "0420 · فرعيّة"
