from __future__ import annotations

from datetime import date

import approval_check as ac
import ledger
import pytest


def test_same_head_ok():
    assert ac.head_status("abcd1234", "abcd1234ffff") == "ok"


def test_changed_head_is_stale():
    assert ac.head_status("abcd1234", "f2901e49") == "stale"


def test_no_head_is_legacy_until_deadline_then_expired():
    assert ac.head_status(None, "f2901e49", date(2026, 10, 9)) == "legacy"
    assert ac.head_status(None, "f2901e49", date(2026, 10, 10)) == "expired"


def test_pr_line_with_other_head_is_stale():
    h = ac.HEAD_IN_LINE.search("اعتُمد من المالك على 8500 — 2026-10-02 — الرأس 0123abcd")
    assert h and ac.head_status(h.group(1), "f2901e49") == "stale"


def test_ledger_approval_requires_head():
    with pytest.raises(ledger.LedgerError):
        ledger.check_head("approved", None)
    assert ledger.check_head("approved", "ABCDEF".lower() + "12") == "abcdef12"
    assert ledger.check_head("pushed", None) is None


def test_waiver_only_for_0501_and_docs(tmp_path):
    p = tmp_path / "ev.jsonl"
    iid = ledger.add_item("owner", "bug", "م", "أ", "ق", path=p, start="2026-10-02T10:00", priority="P2")
    ledger.append_event("state", iid, {"state": "approved", "by": "0501", "head": "aaaa1111"}, p)
    with pytest.raises(ledger.LedgerError):
        ledger.waive_head(iid, "bbbb2222", "0408", "x", path=p, changed=["docs/a.md"])
    with pytest.raises(ledger.LedgerError):
        ledger.waive_head(iid, "bbbb2222", "0501", "x", path=p, changed=["core/permissions.py"])
    ledger.waive_head(iid, "bbbb2222", "0501", "وثيقةٌ فقط", path=p, changed=["docs/a.md"])
    assert ledger.reduce_state(ledger.load_events(p))[iid]["approved_head"] == "bbbb2222"
