"""اختباراتُ تشديد بوّابة المواصفة عند routed (W-20261016-012): الناقصةُ من أيّ طبقةٍ تُرفض للبطاقة الجديدة،
والصغيرةُ بوسم «أساس» تكفيها accept وstep، والاستثناءُ المسجَّل يمرّ، والقديمةُ بتحذيرٍ فقط."""

import tempfile
import unittest
from pathlib import Path

import ledger


def make(path, created, **fields):
    """بطاقةٌ بتاريخ إنشاءٍ محدَّد دون المرور بساعة اليوم."""
    cid = ledger.add_item("owner", "tool", "سكربت صغير", "أ", "ق", start="2026-10-17T08:00", priority="P2", path=path)
    events = ledger.load_events(path)
    for e in events:
        if e["id"] == cid and e["kind"] == "created":
            e["ts"] = created
    import json

    Path(path).write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n", encoding="utf-8")
    if fields:
        ledger.append_event("update", cid, fields, path)
    return cid


class SpecGate(unittest.TestCase):
    def setUp(self):
        self.path = str(Path(tempfile.mkdtemp()) / "e.jsonl")

    def test_new_basic_incomplete_rejected(self):
        cid = make(self.path, "2026-10-16T10:00:00+03:00")
        with self.assertRaises(ledger.LedgerError) as cm:
            ledger.move(cid, "routed", held_by="0301", path=self.path)
        self.assertIn("بطاقةٌ جديدة", str(cm.exception))

    def test_new_basic_with_basic_ok_needs_only_accept_and_steps(self):
        cid = make(self.path, "2026-10-16T10:00:00+03:00", spec_tier="basic", spec_basic_ok="تعديل سطر واحد")
        with self.assertRaises(ledger.LedgerError):
            ledger.move(cid, "routed", held_by="0301", path=self.path)  # بلا accept وsteps
        ledger.append_event("update", cid, {"accept_measurable": ["اختبار يمر"], "steps": ["عدّل"]}, self.path)
        ledger.move(cid, "routed", held_by="0301", path=self.path)
        self.assertEqual(ledger.reduce_state(ledger.load_events(self.path))[cid]["state"], "routed")

    def test_waive_spec_passes_and_is_recorded(self):
        cid = make(self.path, "2026-10-16T10:00:00+03:00")
        ledger.move(cid, "routed", held_by="0301", waive_spec="عاجل بأمر المالك", path=self.path)
        item = ledger.reduce_state(ledger.load_events(self.path))[cid]
        self.assertEqual(item["state"], "routed")
        self.assertTrue(any("استثناءُ المواصفة" in str(n) for n in item.get("notes", [])))

    def test_old_card_still_warns_only(self):
        cid = make(self.path, "2026-10-10T10:00:00+03:00")
        ledger.move(cid, "routed", held_by="0301", path=self.path)  # قبل السريان: تحذير لا رفض
        self.assertEqual(ledger.reduce_state(ledger.load_events(self.path))[cid]["state"], "routed")

    def test_set_spec_records_basic_ok(self):
        cid = make(self.path, "2026-10-16T10:00:00+03:00")
        data = ledger.set_spec(cid, "basic", by="0301", path=self.path, basic_ok="سطر واحد")
        self.assertEqual(data["spec_basic_ok"], "سطر واحد")


if __name__ == "__main__":
    unittest.main()
