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
    assert "اقتربت من الحدّ" in capsys.readouterr().out
    monkeypatch.setattr(si, "app_title", lambda *a, **k: (None, []))
    before = (tmp_path / "msg_counter.json").read_text(encoding="utf-8")
    mc.hook(json.dumps(_payload("(delivery: delivered; message_id: 2)")))
    assert (tmp_path / "msg_counter.json").read_text(encoding="utf-8") == before
