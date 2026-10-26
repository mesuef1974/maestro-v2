from __future__ import annotations

import json

import msg_counter as mc
import session_identity as si


def _payload(text, tool="mcp__ccd_session_mgmt__send_message", **kw):
    return {"tool_name": tool, "tool_response": text, "cwd": "C:/x", "session_id": "s1", **kw}


def test_sent_ok_counts_delivered_and_queued_only():
    assert mc.sent_ok(_payload("Message delivered to session X (delivery: delivered; message_id: 1)"))
    assert mc.sent_ok(_payload({"content": [{"type": "text", "text": "queued (delivery: queued; message_id: 2)"}]}))
    assert not mc.sent_ok(_payload("Error: session not found"))
    assert not mc.sent_ok(_payload("(delivery: undelivered; why)"))
    assert not mc.sent_ok(_payload({"is_error": True, "content": "delivery: delivered"}))
    assert not mc.sent_ok(_payload("delivery: delivered", tool="Bash"))


def test_hook_increments_sender_once_on_success_and_not_on_failure(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(mc, "STATE", tmp_path / "msg_counter.json")
    monkeypatch.setattr(si, "app_title", lambda cwd, sid="", base=None, wait_s=0, **k: ("0301 · الحوكمة", []))
    ok = json.dumps(_payload("(delivery: delivered; message_id: 1)"))
    bad = json.dumps(_payload("Error: cannot send"))
    assert mc.hook(ok) == 0 and mc.hook(bad) == 0 and mc.hook("not json") == 0
    assert json.loads((tmp_path / "msg_counter.json").read_text(encoding="utf-8"))["sessions"]["0301"]["count"] == 1
    assert capsys.readouterr().out == ""  # دون عتبة التنبيه


def test_hook_warns_at_threshold_and_skips_unknown_sender(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(mc, "STATE", tmp_path / "msg_counter.json")
    (tmp_path / "msg_counter.json").write_text(json.dumps({"limit": 600, "started": "x", "sessions": {"0301": {"count": mc.WARN_AT - 1, "since": "x"}}}), encoding="utf-8")
    monkeypatch.setattr(si, "app_title", lambda *a, **k: ("0301 · الحوكمة", []))
    mc.hook(json.dumps(_payload("(delivery: delivered; message_id: 1)")))
    assert "اقتربت من الحدّ" in json.loads(capsys.readouterr().out)["hookSpecificOutput"]["additionalContext"]
    monkeypatch.setattr(si, "app_title", lambda *a, **k: (None, []))
    before = (tmp_path / "msg_counter.json").read_text(encoding="utf-8")
    mc.hook(json.dumps(_payload("(delivery: delivered; message_id: 2)")))
    assert (tmp_path / "msg_counter.json").read_text(encoding="utf-8") == before


def _tx(tmp_path, rows):
    p = tmp_path / "t.jsonl"
    p.write_text(chr(10).join(json.dumps(r, ensure_ascii=False) for r in rows) + chr(10), encoding="utf-8")
    return str(p)


def _user(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


def _send(i):
    return [{"type": "assistant", "message": {"content": [{"type": "tool_use", "id": f"t{i}", "name": "mcp__ccd_session_mgmt__send_message"}]}},
            {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": f"t{i}", "content": "(delivery: delivered; message_id: x)"}]}}]


def test_sends_since_owner_resets_on_real_user_message_only(tmp_path):
    rows = [*_send(1), *_send(2), _user("اعتمد"), *_send(3), *_send(4), _user("<cross-session-message from=x>hi</cross-session-message>"),
            {"type": "user", "message": {"content": [{"type": "text", "text": "<system-reminder>x</system-reminder>"}]}}, *_send(5)]
    assert mc.sends_since_owner(_tx(tmp_path, rows)) == 3  # 3 و4 و5 بعد «اعتمد»؛ رسالةُ الجلسة والتذكير لا تصفّران
    bad = {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t9", "content": "Error"}]}}
    assert mc.sends_since_owner(_tx(tmp_path, [_user("a"), *_send(1), bad])) == 1
    assert mc.sends_since_owner(str(tmp_path / "missing.jsonl")) == 0


def test_sends_since_owner_counts_current_call_not_yet_in_transcript(tmp_path):
    p = _tx(tmp_path, [_user("a"), *_send(1)])
    assert mc.sends_since_owner(p, "t2") == 2 and mc.sends_since_owner(p, "t1") == 1


def test_hook_warns_at_eighth_send_since_owner(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(mc, "STATE", tmp_path / "msg_counter.json")
    monkeypatch.setattr(si, "app_title", lambda *a, **k: ("0301 · الحوكمة", []))
    rows = [_user("ابدأ")]
    for i in range(1, 8):
        rows += _send(i)
    payload = _payload("(delivery: delivered; message_id: 8)", transcript_path=_tx(tmp_path, rows), tool_use_id="t8")
    mc.hook(json.dumps(payload))
    out = json.loads(capsys.readouterr().out)["hookSpecificOutput"]["additionalContext"]
    assert "حدّ التطبيق" in out and "8 رسائل" in out
