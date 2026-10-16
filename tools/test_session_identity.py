from __future__ import annotations

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
    msg = capsys.readouterr().out
    assert "delivered` = مبلّغة" in msg and "queued` = في الطابور فلا تُعاد" in msg
    assert "بعد دقيقتين من list_events" in msg and "مرةً واحدةً" in msg
    assert "undelivered` = لم تبلغ فأعِد الإرسال بعد دقيقة" in msg
    assert "(بلغت / في الطابور / لم تبلغ)" in msg and "ولا تسأل المالكَ عن إعادة الإرسال" in msg
