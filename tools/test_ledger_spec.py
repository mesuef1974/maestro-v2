"""اختباراتُ بوّابة المواصفة الكاملة:  python -m pytest test_ledger_spec.py"""

import json
import tempfile
import unittest
from pathlib import Path

import intake_kpis
import ledger

FULL = dict(ref="طبق الأصل|templates/a.html|http://localhost:8500/a|معلّم|snap/a.png", assumptions=["محسوم: نصّ المالك 10-04", "افتراض: الخروج ليس غياباً"],
            source_of_truth="لائحة الوزارة م٣", files_allowed=["templates/a.html"], files_forbidden=["core/"], accept=["لقطة 768"], steps=["اقرأ"], by="0301")


class Spec(unittest.TestCase):
    def setUp(self):
        self.path = str(Path(tempfile.mkdtemp()) / "e.jsonl")

    def card(self, typ="ui", **kw):
        return ledger.add_item("owner", typ, kw.get("problem", "م"), "أ", "ق", start="2026-10-05T08:00", priority="P2", path=self.path)

    def test_inference_rules(self):
        self.assertEqual(ledger.infer_spec_tier({"type": "ui"})[0], "full")
        self.assertEqual(ledger.infer_spec_tier({"type": "tool", "problem": "هجرة جديدة"})[0], "full")
        self.assertEqual(ledger.infer_spec_tier({"type": "tool", "problem": "صلاحيات"})[0], "full")
        self.assertEqual(ledger.infer_spec_tier({"type": "tool", "accept": "طبق الأصل"})[0], "full")
        self.assertEqual(ledger.infer_spec_tier({"type": "tool", "files": ["worktrees/a/x.py", "worktrees/b/y.py"]})[0], "full")
        self.assertEqual(ledger.infer_spec_tier({"type": "tool", "problem": "سكربت"})[0], "basic")

    def test_full_card_rejected_until_complete(self):
        cid = self.card()
        with self.assertRaises(ledger.LedgerError) as cm:
            ledger.move(cid, "routed", path=self.path)
        self.assertIn("files_allowed", str(cm.exception))
        with self.assertRaises(ledger.LedgerError):
            ledger.move(cid, "in_progress", path=self.path)
        ledger.set_spec(
            cid, "full", FULL["ref"], None, None, FULL["assumptions"], FULL["source_of_truth"], FULL["files_allowed"],
            FULL["files_forbidden"], FULL["accept"], FULL["steps"], "0301", self.path)
        ledger.move(cid, "routed", path=self.path)
        it = ledger.reduce_state(ledger.load_events(self.path))[cid]
        self.assertEqual(it["spec_by"], "0301")
        self.assertIn("مكتملة", ledger.spec_status(it))
        ledger.move(cid, "in_progress", path=self.path)

    def test_waive_is_recorded(self):
        cid = self.card()
        ledger.move(cid, "routed", path=self.path, waive_spec="عاجلٌ بأمر المالك")
        notes = ledger.reduce_state(ledger.load_events(self.path))[cid]["notes"]
        self.assertTrue(any("استثناءُ المواصفة" in n["text"] for n in notes))

    def test_basic_only_warns(self):
        cid = self.card("tool", problem="سكربت")
        ledger.move(cid, "routed", path=self.path)

    def test_open_assumption_must_be_declared(self):
        cid = self.card()
        with self.assertRaises(ledger.LedgerError):
            ledger.set_spec(cid, assumptions=["؟ لا أدري"], by="0301", path=self.path)

    def test_no_downgrade_and_steps_cap(self):
        cid = self.card()
        with self.assertRaises(ledger.LedgerError):
            ledger.set_spec(cid, "basic", by="0301", path=self.path)
        with self.assertRaises(ledger.LedgerError):
            ledger.set_spec(cid, steps=[str(i) for i in range(8)], by="0301", path=self.path)

    def test_return_and_kpi(self):
        cid = self.card("tool", problem="سكربت")
        ledger.move(cid, "routed", path=self.path)
        ledger.return_card(cid, "ينقصها المرجع", "0501", self.path)
        events = ledger.load_events(self.path)
        it = ledger.reduce_state(events)[cid]
        self.assertEqual(it["state"], "captured")
        self.assertEqual(intake_kpis.compute({cid: it}, events)["0201"]["returned_for_spec"], 1)
        with self.assertRaises(ledger.LedgerError):
            ledger.return_card(cid, "", "0501", self.path)

    def test_old_cards_are_basic(self):
        self.assertEqual(ledger.effective_spec_tier({"created": "2026-10-01T08:00:00+03:00", "type": "ui"}), "basic")


if __name__ == "__main__":
    unittest.main()
