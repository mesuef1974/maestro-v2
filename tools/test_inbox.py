from __future__ import annotations

import json

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


def test_wait_returns_incoming_at_once_acks_and_removes_beat(tmp_path):
    inbox.send("0301", "0101", "جاهز", tmp_path)
    msgs = inbox.wait("0301", tmp_path, sleep=lambda s: pytest.fail("لا نوم والواردُ حاضر"))
    assert [m["text"] for m in msgs] == ["جاهز"]
    assert inbox.pending("0301", tmp_path) == []
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
