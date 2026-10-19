"""اختباراتُ ختم التحقق من مصدر الحقيقة وبوّابة الظلّ (W-20261020-003): تُنذر ولا تحجب أبدًا."""

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import ledger

HEAD = "a1b2c3d4"
EV = ["git rev-list --count origin/main..X => 752"]


class SotGate(unittest.TestCase):
    def setUp(self):
        self.path = str(Path(tempfile.mkdtemp()) / "e.jsonl")
        self.cid = ledger.add_item("owner", "tool", "سكربت", "أ", "ق", start="2026-10-20T09:00", priority="P2", path=self.path)

    def item(self):
        return ledger.reduce_state(ledger.load_events(self.path))[self.cid]

    def stamp(self, verdict="مطابق", head=HEAD, **kw):
        return ledger.set_sot_stamp(self.cid, verdict, head, EV, "0301", path=self.path, **kw)

    def test_no_stamp_warns_on_in_progress(self):
        w = ledger.check_sot_gate(self.item(), "in_progress")
        self.assertIn("لا ختمَ", w)
        self.assertIn(ledger.SOT_MARK, w)

    def test_fresh_matching_stamp_passes(self):
        self.stamp()
        self.assertIsNone(ledger.check_sot_gate(self.item(), "in_progress", head_now=HEAD))

    def test_stale_stamp_warns(self):
        self.stamp()
        later = datetime.fromisoformat(self.item()["sot_stamp"]["at"]) + timedelta(days=8)
        self.assertIn("أقدمُ من 7", ledger.check_sot_gate(self.item(), "in_progress", now=later))

    def test_changed_head_warns(self):
        self.stamp()
        self.assertIn("تغيّر الرأسُ", ledger.check_sot_gate(self.item(), "in_progress", head_now="ffffffff"))

    def test_stale_verdict_warns(self):
        self.stamp("متقادم")
        self.assertIn("متقادم", ledger.check_sot_gate(self.item(), "in_progress"))

    def test_mismatch_requires_correction_and_adds_note(self):
        with self.assertRaises(ledger.LedgerError):
            self.stamp("مخالف")
        self.stamp("مخالف", correction="الرقم الصحيح 752 لا 46")
        self.assertTrue(any("ختمُ المصدر مخالف" in n["text"] for n in self.item()["notes"]))
        self.assertIsNone(ledger.check_sot_gate(self.item(), "in_progress"))

    def test_remeasure_warning_before_ready(self):
        self.stamp()
        self.assertIn("إعادةُ قياس", ledger.check_sot_gate(self.item(), "ready_for_review"))
        self.stamp(remeasure=True)
        self.assertIsNone(ledger.check_sot_gate(self.item(), "ready_for_review"))

    def test_other_targets_ignored(self):
        self.assertIsNone(ledger.check_sot_gate(self.item(), "routed"))

    def test_move_never_blocks_and_logs_warning(self):
        ledger.move(self.cid, "routed", held_by="0103", waive_spec="اختبار", path=self.path)
        ledger.move(self.cid, "in_progress", by="0103", waive_spec="اختبار", waive_wip="اختبار", path=self.path)
        self.assertEqual(self.item()["state"], "in_progress")
        self.assertTrue(any(ledger.SOT_MARK in n["text"] for n in self.item()["notes"]))

    def test_bad_inputs_rejected(self):
        with self.assertRaises(ledger.LedgerError):
            ledger.set_sot_stamp(self.cid, "غير", HEAD, EV, "0301", path=self.path)
        with self.assertRaises(ledger.LedgerError):
            ledger.set_sot_stamp(self.cid, "مطابق", "zz", EV, "0301", path=self.path)
        with self.assertRaises(ledger.LedgerError):
            ledger.set_sot_stamp(self.cid, "مطابق", HEAD, ["بلا فاصل"], "0301", path=self.path)


if __name__ == "__main__":
    unittest.main()
