from __future__ import annotations

import json
import os
import time

import pytest

import inbox


def test_send_read_acks_and_is_idempotent(tmp_path):
    a = inbox.send("0301", "0101", "مهمّة أولى", tmp_path)
    b = inbox.send("0301", "0101", "مهمّة ثانية", tmp_path)
    assert (a, b) == (1, 2)
    assert [m["id"] for m in inbox.read("0301", False, tmp_path)] == [1, 2]  # peek لا يُسلّم
    assert [m["text"] for m in inbox.read("0301", True, tmp_path)] == ["مهمّة أولى", "مهمّة ثانية"]
    assert inbox.read("0301", True, tmp_path) == []  # سُلِّمتا مرّةً واحدة
    assert inbox.send("0301", "0101", "ثالثة", tmp_path) == 3  # الترقيم لا يعود إلى الصفر


def test_send_rejects_bad_input(tmp_path):
    for to, frm, text in (("xx", "0101", "a"), ("0301", "bad", "a"), ("0301", "0101", "  "), ("0301", "0101", "ح" * (inbox.MAX_TEXT + 1))):
        with pytest.raises(ValueError):
            inbox.send(to, frm, text, tmp_path)


def test_pending_nums_lists_only_boxes_with_unacked(tmp_path):
    inbox.send("0301", "0101", "a", tmp_path)
    inbox.send("0501", "0101", "b", tmp_path)
    inbox.read("0501", True, tmp_path)
    assert inbox.pending_nums(tmp_path) == {"0301": 1}


def test_claim_block_once_per_batch(tmp_path):
    inbox.send("0301", "0101", "أولى", tmp_path)
    assert [m["id"] for m in inbox.claim_block("0301", tmp_path)] == [1]
    assert inbox.claim_block("0301", tmp_path) == []  # لا حلقةَ منع
    inbox.send("0301", "0101", "ثانية", tmp_path)  # دفعةٌ جديدة
    assert [m["id"] for m in inbox.claim_block("0301", tmp_path)] == [2]
    assert inbox.pending("0301", tmp_path) == []


def test_hook_injects_inbox_and_acks_then_stays_silent(tmp_path):
    inbox.send("0301", "0101", "نفّذ 015", tmp_path)
    out = json.loads(inbox.hook("{}", tmp_path, resolve=lambda p: "0301"))
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "PostToolUse" and "نفّذ 015" in ctx and "من 0101" in ctx
    assert inbox.hook("{}", tmp_path, resolve=lambda p: "0301") == ""
    assert inbox.hook("{}", tmp_path, resolve=lambda p: None) == ""
    assert inbox.hook("not json", tmp_path, resolve=lambda p: (_ for _ in ()).throw(RuntimeError())) == ""


def test_hook_batches_at_show_max_and_reports_remainder(tmp_path):
    for i in range(inbox.SHOW_MAX + 2):
        inbox.send("0301", "0101", f"م{i}", tmp_path)
    ctx = json.loads(inbox.hook("{}", tmp_path, resolve=lambda p: "0301"))["hookSpecificOutput"]["additionalContext"]
    assert "+2 أخرى" in ctx and len(inbox.pending("0301", tmp_path)) == 2


def test_cli_send_and_read(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(inbox, "ROOT", tmp_path)
    assert inbox.main(["send", "--to", "0301", "--from", "0101", "--text", "مرحبا"]) == 0
    assert inbox.main(["read", "0301", "--peek"]) == 0
    assert "مرحبا" in capsys.readouterr().out
    assert inbox.main(["send", "--to", "0301", "--from", "bad", "--text", "x"]) == 3


def test_subtree_of_governance_uses_main_root_box(tmp_path):
    """W-20261027-001: شجرةُ حوكمةٍ فرعيّة (.claude/worktrees/x) تقرأ وتكتب صندوقَ الجذر ونبضَه."""
    sub = tmp_path / ".claude" / "worktrees" / "x"
    sub.mkdir(parents=True)
    assert inbox.main_root(sub) == tmp_path and inbox.main_root(tmp_path) == tmp_path
    inbox.send("0301", "0101", "للجذر", sub)
    assert [m["text"] for m in inbox.pending("0301", tmp_path)] == ["للجذر"]
    inbox.beat("0301", sub)
    assert inbox.watcher_alive("0301", tmp_path)
    assert not (sub / "ledger").exists()


def test_cli_wait_read_send_use_main_root_from_subtree(tmp_path, monkeypatch, capsys):
    sub = tmp_path / ".claude" / "worktrees" / "x"
    sub.mkdir(parents=True)
    monkeypatch.setattr(inbox, "ROOT", sub)
    assert inbox.main(["send", "--to", "0301", "--from", "0101", "--text", "س"]) == 0
    assert inbox.main(["wait", "0301", "--timeout", "1"]) == 0
    assert "س" in capsys.readouterr().out
    assert (tmp_path / "ledger" / "inbox" / "0301.jsonl").exists() and not (sub / "ledger").exists()


def test_wait_returns_incoming_at_once_without_ack_and_removes_beat(tmp_path):
    inbox.send("0301", "0101", "جاهز", tmp_path)
    msgs = inbox.wait("0301", tmp_path, sleep=lambda s: pytest.fail("لا نوم والواردُ حاضر"))
    assert [m["text"] for m in msgs] == ["جاهز"]
    assert [m["text"] for m in inbox.pending("0301", tmp_path)] == ["جاهز"]  # لا إقرار: read يجده بعد الإيقاظ
    assert [m["text"] for m in inbox.read("0301", True, tmp_path)] == ["جاهز"] and inbox.pending("0301", tmp_path) == []
    assert not inbox.watcher_alive("0301", tmp_path)  # خرج فحُذف نبضُه


def test_wait_polls_beats_then_returns_when_message_arrives(tmp_path):
    seen = []

    def sleep(s):
        seen.append((s, inbox.watcher_alive("0301", tmp_path)))  # النبضُ حيٌّ أثناء الانتظار
        if len(seen) == 3:
            inbox.send("0301", "0101", "وصلت", tmp_path)

    msgs = inbox.wait("0301", tmp_path, interval=2, sleep=sleep)
    assert [m["text"] for m in msgs] == ["وصلت"]
    assert seen == [(2, True)] * 3


def test_wait_timeout_returns_empty(tmp_path):
    t = iter([0, 1, 5, 9])
    assert inbox.wait("0301", tmp_path, timeout=4, sleep=lambda s: None, clock=lambda: next(t)) == []
    assert not inbox.watcher_alive("0301", tmp_path)


def test_watcher_alive_requires_fresh_valid_beat(tmp_path):
    assert not inbox.watcher_alive("0301", tmp_path)  # لا ملف
    inbox.beat("0301", tmp_path)
    assert inbox.watcher_alive("0301", tmp_path)
    import time

    assert not inbox.watcher_alive("0301", tmp_path, now=time.time() + inbox.BEAT_MAX_AGE_S + 5)  # نبضٌ قديم
    inbox._beat_path("0301", tmp_path).write_text("{bad", encoding="utf-8")
    assert not inbox.watcher_alive("0301", tmp_path)  # ملفٌّ تالف


def test_send_cli_warns_when_receiver_has_no_watcher(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(inbox, "ROOT", tmp_path)
    assert inbox.main(["send", "--to", "0501", "--from", "0301", "--text", "س"]) == 0
    assert "send_message" in capsys.readouterr().out
    inbox.beat("0501")
    assert inbox.main(["send", "--to", "0501", "--from", "0301", "--text", "ص"]) == 0
    assert "send_message" not in capsys.readouterr().out


def test_wait_follow_mode_emits_every_batch_and_keeps_looping(tmp_path):
    """W-20261027-006: بلا --once يطبع كلَّ دفعةٍ مرّةً ويواصل حتى المهلة؛ W-20261027-020: ولا يقرّ شيئاً (الإقرارُ لـread)."""
    inbox.send("0301", "0101", "أ", tmp_path)
    seen, arrived = [], []

    def sleep(s):
        if not arrived:
            inbox.send("0301", "0101", "ب", tmp_path)
            arrived.append(1)

    t = iter(range(0, 100, 2))
    got = inbox.wait("0301", tmp_path, timeout=6, sleep=sleep, clock=lambda: next(t), once=False, emit=seen.append)
    assert [m["text"] for m in got] == ["أ", "ب"] and [[m["text"] for m in b] for b in seen] == [["أ"], ["ب"]]
    assert [m["text"] for m in inbox.pending("0301", tmp_path)] == ["أ", "ب"] and not inbox.watcher_alive("0301", tmp_path)
    assert [m["text"] for m in inbox.read("0301", True, tmp_path)] == ["أ", "ب"] and inbox.pending("0301", tmp_path) == []


def test_cli_wait_once_exits_at_first_message(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(inbox, "ROOT", tmp_path)
    inbox.send("0301", "0101", "س", tmp_path)
    assert inbox.main(["wait", "0301", "--once"]) == 0
    assert "س" in capsys.readouterr().out
    assert [m["text"] for m in inbox.pending("0301", tmp_path)] == ["س"]  # W-20261027-001: --once لا يقرّ؛ read يجده بعد الإيقاظ


# ===== W-20261028-033: بصمة الشيفرة ومراقبٌ واحد وreap =====
def test_watcher_exits_with_note_when_code_fingerprint_changes(tmp_path):
    """مراقبٌ بدأ ثمّ تغيّر inbox.py على القرص: يخرج بسطر شرحٍ ويحذف نبضَه ولا يقرّ شيئاً."""
    inbox.send("0301", "0101", "أ", tmp_path)
    fps = iter(["aaa", "aaa", "bbb"])
    notes = []
    inbox.wait("0301", tmp_path, once=False, sleep=lambda s: None, fingerprint=lambda: next(fps), note=notes.append)
    assert len(notes) == 1 and "تغيّر inbox.py" in notes[0] and "aaa" in notes[0]
    assert [m["text"] for m in inbox.pending("0301", tmp_path)] == ["أ"]  # لم يُقرّ
    assert not inbox.watcher_alive("0301", tmp_path)


def test_second_watcher_for_same_number_exits_without_touching_first_beat(tmp_path, monkeypatch):
    p = inbox._beat_path("0301", tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"pid": os.getpid() + 1, "t": time.time()}), encoding="utf-8")
    notes = []
    assert inbox.wait("0301", tmp_path, once=False, sleep=lambda s: None, note=notes.append) == []
    assert len(notes) == 1 and "مراقبٌ آخر حيٌّ" in notes[0] and str(os.getpid() + 1) in notes[0]
    assert json.loads(p.read_text(encoding="utf-8"))["pid"] == os.getpid() + 1  # نبضُ الأول سليم


def test_stale_beat_does_not_block_a_new_watcher(tmp_path):
    p = inbox._beat_path("0301", tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"pid": os.getpid() + 1, "t": time.time() - 100}), encoding="utf-8")
    inbox.send("0301", "0101", "س", tmp_path)
    assert [m["text"] for m in inbox.wait("0301", tmp_path, sleep=lambda s: None)] == ["س"]


def test_reap_stops_fresh_watchers_of_dead_numbers_and_drops_stale_beats(tmp_path):
    def mk(num, pid, age):
        q = inbox._beat_path(num, tmp_path)
        q.parent.mkdir(parents=True, exist_ok=True)
        q.write_text(json.dumps({"pid": pid, "t": time.time() - age}), encoding="utf-8")

    mk("0301", 111, 1)   # حيّ ورقمه حيّ: يبقى
    mk("0409", 222, 1)   # رقمٌ غير حيّ ونبضُه طازج: يُوقَف
    mk("0426", 333, 100)  # رقمٌ غير حيّ ونبضُه قديم: يُحذف ملفُّه فقط
    killed = []
    out = inbox.reap({"0301"}, tmp_path, kill=lambda pid, sig: killed.append(pid))
    assert killed == [222] and len(out) == 2
    assert inbox._beat_path("0301", tmp_path).exists()
    assert not inbox._beat_path("0409", tmp_path).exists() and not inbox._beat_path("0426", tmp_path).exists()


def test_cli_reap_uses_session_directory(tmp_path, monkeypatch, capsys):
    import session_directory

    monkeypatch.setattr(inbox, "ROOT", tmp_path)
    monkeypatch.setattr(session_directory, "entries", lambda: {"0301": {}})
    assert inbox.main(["reap"]) == 0
    assert "لا مراقبَ" in capsys.readouterr().out


def test_send_to_a_merged_number_lands_in_its_receivers_inbox(tmp_path, monkeypatch):
    """(10-29) 0420 مدمَجة في 0409: رسالةٌ إلى 0420 كانت تبقى في صندوقٍ بلا جلسةٍ ولا تُقرأ."""
    import session_alias

    monkeypatch.setattr(session_alias, "number_map", lambda tabs=None: {"0420": "0409"})
    inbox.send("0420", "0101", "x", root=tmp_path)
    assert len(inbox.pending("0409", root=tmp_path)) == 1
    assert inbox.pending("0420", root=tmp_path) == []
