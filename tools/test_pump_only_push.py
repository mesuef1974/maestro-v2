"""حارسُ «الدفع من المضخّة وحدها» (W-20261023-003، الموجة 0.8) — بلا شبكةٍ."""

from __future__ import annotations

import json

import ledger
import pytest

APPROVED = {"state": "approved"}


def test_manual_push_of_approved_card_warns_in_shadow(monkeypatch):
    monkeypatch.delenv("PUMP_ONLY_PUSH_ENFORCE", raising=False)
    msg = ledger.check_pump_only_push(APPROVED, "pushed", False, None)
    assert msg and msg.startswith("إنذار (الظلّ)") and "push_approved.py" in msg


def test_manual_push_is_refused_when_enforced(monkeypatch):
    monkeypatch.setenv("PUMP_ONLY_PUSH_ENFORCE", "1")
    with pytest.raises(ledger.LedgerError, match="push_approved"):
        ledger.check_pump_only_push(APPROVED, "pushed", False, None)


def test_pump_push_and_waiver_pass_even_when_enforced(monkeypatch):
    monkeypatch.setenv("PUMP_ONLY_PUSH_ENFORCE", "1")
    assert ledger.check_pump_only_push(APPROVED, "pushed", True, None) is None
    assert "استثناء" in ledger.check_pump_only_push(APPROVED, "pushed", False, "تعطّل المضخّة")


def test_other_states_and_transitions_are_untouched(monkeypatch):
    monkeypatch.setenv("PUMP_ONLY_PUSH_ENFORCE", "1")
    assert ledger.check_pump_only_push(APPROVED, "merged", False, None) is None
    assert ledger.check_pump_only_push({"state": "in_progress"}, "pushed", False, None) is None


def _ledger_with_approved(tmp_path):
    path = tmp_path / "events.jsonl"
    ts = "2026-10-23T00:00:00+03:00"
    events = [
        {"ts": ts, "id": "W-1", "kind": "created", "data": {"title": "t", "type": "tools"}},
        {"ts": ts, "id": "W-1", "kind": "state", "data": {"state": "approved", "head": "abcd1234", "by": "0101"}},
    ]
    path.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n", encoding="utf-8")
    return path


def test_move_pushed_by_hand_is_refused_when_enforced_and_allowed_via_pump(tmp_path, monkeypatch):
    path = _ledger_with_approved(tmp_path)
    monkeypatch.setenv("PUMP_ONLY_PUSH_ENFORCE", "1")
    with pytest.raises(ledger.LedgerError, match="push_approved"):
        ledger.move("W-1", "pushed", path=path, by="0501", head="abcd1234", branch="claude/x", remote_lookup=lambda _b: "abcd1234ff")
    ledger.move("W-1", "pushed", path=path, by="0701", head="abcd1234", branch="claude/x", remote_lookup=lambda _b: "abcd1234ff", via_pump=True)
    assert ledger.reduce_state(ledger.load_events(path))["W-1"]["state"] == "pushed"
