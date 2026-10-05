"""اختباراتُ قائمة المالك — بلا شبكة."""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import ledger
import owner_queue as oq

NOW = datetime.fromisoformat("2026-10-06T12:00:00+03:00")


def item(i, state, pr, ts):
    return {"id": i, "state": state, "priority": pr, "state_ts": ts, "problem": f"مشكلة {i}"}


class Queue(unittest.TestCase):
    def setUp(self):
        self.p = Path(tempfile.mkdtemp()) / "d.jsonl"

    def test_limit_order_and_more(self):
        items = {n: item(n, "ready_for_review", pr, ts) for n, pr, ts in [
            ("A", "P2", "2026-10-01T10:00:00+03:00"), ("B", "P1", "2026-10-05T10:00:00+03:00"),
            ("C", "P1", "2026-10-03T10:00:00+03:00"), ("D", "P3", "2026-10-01T10:00:00+03:00"),
            ("E", "P0", "2026-10-06T10:00:00+03:00")]}
        q = oq.build(items, [], NOW)
        self.assertEqual([r["id"] for r in q["shown"]], ["E", "C", "B"])
        self.assertEqual(q["more"], 2)
        self.assertIn("والمزيد: 2", oq.render(q))

    def test_approved_separate_and_uncounted(self):
        items = {"X": item("X", "approved", "P0", "2026-10-05T12:00:00+03:00")}
        q = oq.build(items, [], NOW)
        self.assertEqual((q["total"], len(q["awaiting_push"])), (0, 1))
        self.assertIn("ينتظر الدفعَ", oq.render(q))

    def test_decisions_lifecycle_and_merge(self):
        oq.decision_add("D-1", "هل نؤجل؟", ["نعم", "لا"], path=self.p, now=NOW)
        with self.assertRaises(ledger.LedgerError):
            oq.decision_add("D-1", "س", ["أ"], path=self.p)
        q = oq.build({"A": item("A", "ready_for_review", "P2", "2026-10-01T10:00:00+03:00")}, oq.open_decisions(self.p), NOW)
        self.assertEqual([r["id"] for r in q["shown"]], ["D-1", "A"])
        oq.decision_close("D-1", "نعم", path=self.p)
        self.assertEqual(oq.open_decisions(self.p), [])
        with self.assertRaises(ledger.LedgerError):
            oq.decision_close("D-1", "x", path=self.p)
        with self.assertRaises(ledger.LedgerError):
            oq.decision_close("D-9", "x", path=self.p)

    def test_empty_and_age(self):
        self.assertIn("لا شيء", oq.render(oq.build({}, [], NOW)))
        self.assertEqual(oq.age_text("2026-10-06T09:00:00+03:00", NOW), "3 ساعة")
        self.assertEqual(oq.age_text("2026-10-01T12:00:00+03:00", NOW), "5 يوم")


if __name__ == "__main__":
    unittest.main()
