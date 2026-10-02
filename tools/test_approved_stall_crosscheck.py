from __future__ import annotations

from datetime import datetime, timedelta, timezone

import ledger
import watch_once as w

DOHA = timezone(timedelta(hours=3))


def _approved(monkeypatch, tmp_path):
    p = tmp_path / "ev.jsonl"
    iid = ledger.add_item("owner", "bug", "م", "أ", "ق", path=p, start="2026-10-02T10:00", priority="P2")
    ledger.append_event("state", iid, {"state": "approved", "by": "0501", "head": "aaaa1111"}, p)
    monkeypatch.setattr(ledger, "load_events", lambda path=None: ledger.__dict__["_orig_load"](p))
    return iid


def _run(monkeypatch, tmp_path, prs):
    ledger.__dict__["_orig_load"] = ledger.__dict__.get("_orig_load", ledger.load_events)
    _approved(monkeypatch, tmp_path)
    later = datetime.now(DOHA) + timedelta(hours=5)
    return w.approved_stall_alerts(now=later, pr_lookup=lambda c: prs)


def test_merged_pr_means_ledger_lag_not_push_delay(monkeypatch, tmp_path):
    out = _run(monkeypatch, tmp_path, [{"number": 9, "state": "MERGED"}])
    assert [a["code"] for a in out] == ["ledger_lag"]


def test_open_pr_is_info_only(monkeypatch, tmp_path):
    out = _run(monkeypatch, tmp_path, [{"number": 9, "state": "OPEN"}])
    assert [a["code"] for a in out] == ["approved_pr_open"]


def test_no_pr_is_real_push_delay(monkeypatch, tmp_path):
    out = _run(monkeypatch, tmp_path, [])
    assert [a["code"] for a in out] == ["approved_not_pushed"]
