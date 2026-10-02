from __future__ import annotations

from datetime import datetime, timedelta

import intake_kpis as k
import ledger


def _mk(tmp_path, source="owner"):
    p = tmp_path / "ev.jsonl"
    iid = ledger.add_item(source, "bug", "م", "أ", "ق", path=p, start="2026-10-01T10:00", priority="P2")
    return p, iid


def test_parked_by_decision_is_counted_separately(tmp_path):
    p, a = _mk(tmp_path)
    ledger.add_item("owner", "bug", "م2", "أ", "ق", path=p, start="2026-10-01T10:00", priority="P2")
    ledger.park(a, "D-120م", "حزمةُ الامتثال الرجعيّ مؤجَّلة", path=p)
    now = datetime.now(ledger.DOHA) + timedelta(hours=48)
    out = k.compute(ledger.reduce_state(ledger.load_events(p)), ledger.load_events(p), now)["0204"]
    assert (out["captured_older_24h"], out["captured_older_24h_parked_by_decision"], out["captured_older_24h_unparked"]) == (2, 1, 1)


def test_park_needs_a_real_decision_number(tmp_path):
    import pytest
    p, a = _mk(tmp_path)
    with pytest.raises(ledger.LedgerError):
        ledger.park(a, "قرارٌ ما", "x", path=p)


def test_false_alarm_ratio_uses_fixed_note(tmp_path):
    p, a = _mk(tmp_path, "alert")
    ledger.add_item("alert", "bug", "م2", "أ", "ق", path=p, start="2026-10-01T10:00", priority="P2")
    ledger.append_event("note", a, {"text": f"أُغلق: {ledger.FALSE_ALARM_NOTE} (عتبةٌ خاطئة)"}, p)
    out = k.compute(ledger.reduce_state(ledger.load_events(p)), ledger.load_events(p))["0203"]
    assert out["false_alarm_cards"] == 1 and out["false_alarm_ratio"] == 0.5
