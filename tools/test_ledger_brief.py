"""اختبار --brief لـledger show وmy_state (W-20261013-033): ≤12 سطراً، والافتراضي لا يتغيّر. بلا اعتماد على بيانات الدفتر الحيّ."""
from __future__ import annotations

import sys
from pathlib import Path

T = Path(__file__).resolve().parent
sys.path.insert(0, str(T))
import ledger  # noqa: E402
import my_state  # noqa: E402

LONG = "نص طويل " * 200
FULL = {
    "id": "W-1", "priority": "P2", "state": "captured", "problem": LONG, "origin": "owner-order",
    "owner_order_at": "2026-10-13T21:00", "held_by": "0301", "approvals": [], "notes": [{"text": LONG}],
    "ref": {"path": LONG}, "files_allowed": ["a", "b", "c", "d"], "steps": [LONG], "accept_measurable": [LONG],
}


def test_brief_lines_full_card_max_12():
    out = ledger.brief_lines(FULL, "W-1")
    assert 1 < len(out) <= 12 and out[0].startswith("W-1")
    assert all(len(line) < 400 for line in out)


def test_brief_lines_sparse_card_max_12():
    out = ledger.brief_lines({"id": "W-2", "state": "captured"}, "W-2")
    assert len(out) <= 12


def test_brief_lines_missing_card():
    assert ledger.brief_lines(None, "X") == ["بطاقةٌ غيرُ موجودة: X"]


def test_my_state_brief_empty_and_max_12():
    assert len(my_state.brief_report("0301", []).splitlines()) <= 12
    ev = ledger.load_events()
    for s in ("0301", "0103", "0401"):
        assert len(my_state.brief_report(s, ev).splitlines()) <= 12
