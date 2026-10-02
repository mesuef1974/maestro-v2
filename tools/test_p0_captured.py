from __future__ import annotations

from datetime import datetime, timedelta

import ledger
import watch_once as w


def _setup(monkeypatch, tmp_path, prio="P0", state=None):
    p = tmp_path / "ev.jsonl"
    iid = ledger.add_item("owner", "bug", "م", "أ", "ق", path=p, start="2026-10-01T10:00", priority=prio, urgent=(prio == "P0"))
    if state:
        ledger.append_event("state", iid, {"state": state, "by": "0101"}, p)
    monkeypatch.setattr(ledger, "load_events", lambda path=None: ledger.__dict__["_orig"](p))
    return iid


def _run(monkeypatch, tmp_path, hours, **kw):
    ledger.__dict__.setdefault("_orig", ledger.load_events)
    _setup(monkeypatch, tmp_path, **kw)
    return w.p0_captured_alerts(now=datetime.now(w.DOHA) + timedelta(hours=hours))


def test_stalled_p0_alerts_the_maestro(monkeypatch, tmp_path):
    out = _run(monkeypatch, tmp_path, 2)
    assert [a["code"] for a in out] == ["p0_captured"] and out[0]["severity"] == "high"


def test_fresh_p0_is_quiet(monkeypatch, tmp_path):
    assert _run(monkeypatch, tmp_path, 0.2) == []


def test_non_p0_or_started_is_quiet(monkeypatch, tmp_path):
    assert _run(monkeypatch, tmp_path, 5, prio="P1") == []
    assert _run(monkeypatch, tmp_path, 5, state="in_progress") == []


def test_raise_priority_only_raises(tmp_path):
    import pytest
    p = tmp_path / "ev.jsonl"
    iid = ledger.add_item("owner", "bug", "م", "أ", "ق", path=p, start="2026-10-01T10:00", priority="P3")
    ledger.raise_priority(iid, "P2", "جلستان بلا مُطلِق", "0102", path=p)
    assert ledger.reduce_state(ledger.load_events(p))[iid]["priority"] == "P2"
    with pytest.raises(ledger.LedgerError):
        ledger.raise_priority(iid, "P3", "خفض", "0102", path=p)
