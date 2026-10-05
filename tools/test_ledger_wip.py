"""اختباراتُ بوّابة حدِّ العمل الجاري (WIP) في الدفتر."""

import tempfile
import unittest
from pathlib import Path

import ledger
from ledger import LedgerError


def _card(path, ts, priority="P1", n=[0]):
    n[0] += 1
    iid = f"W-T-{n[0]:03d}"
    ledger.append_event("created", iid, {"priority": priority, "type": "ui", "problem": "p"}, path)
    # نُعدّل زمنَ الإنشاء ليُحاكي بطاقةً قديمة/جديدة
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    import json
    ev = json.loads(lines[-1]); ev["ts"] = ts
    lines[-1] = json.dumps(ev, ensure_ascii=False)
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return iid


def mv(*a, **k):
    k.setdefault("waive_spec", "اختبار")  # نعزل بوّابة WIP عن بوّابة المواصفة
    return ledger.move(*a, **k)


NEW = "2026-10-06T09:00:00+03:00"
OLD = "2026-10-04T09:00:00+03:00"


class Wip(unittest.TestCase):
    def setUp(self):
        self.p = Path(tempfile.mkdtemp()) / "events.jsonl"

    def items(self):
        return ledger.reduce_state(ledger.load_events(self.p))

    def test_second_new_card_rejected(self):
        a, b = _card(self.p, NEW), _card(self.p, NEW)
        mv(a, "in_progress", self.p, by="0301")
        with self.assertRaises(LedgerError) as cx:
            mv(b, "in_progress", self.p, by="0301")
        self.assertIn(a, str(cx.exception))

    def test_old_card_exempt(self):
        a, b = _card(self.p, NEW), _card(self.p, OLD)
        mv(a, "in_progress", self.p, by="0301")
        mv(b, "in_progress", self.p, by="0301")

    def test_p0_exempt(self):
        a, b = _card(self.p, NEW), _card(self.p, NEW, "P0")
        mv(a, "in_progress", self.p, by="0301")
        mv(b, "in_progress", self.p, by="0301")

    def test_waiver_recorded_as_note(self):
        a, b = _card(self.p, NEW), _card(self.p, NEW)
        mv(a, "in_progress", self.p, by="0301")
        mv(b, "in_progress", self.p, by="0301", waive_wip="انتظار مراجعة")
        self.assertTrue(any("انتظار مراجعة" in n["text"] for n in self.items()[b]["notes"]))

    def test_different_sessions_no_conflict(self):
        a, b = _card(self.p, NEW), _card(self.p, NEW)
        mv(a, "in_progress", self.p, by="0301")
        mv(b, "in_progress", self.p, by="0302")

    def test_session_in_progress_function(self):
        a = _card(self.p, NEW)
        mv(a, "in_progress", self.p, by="0301")
        self.assertEqual([i["id"] for i in ledger.session_in_progress(self.items(), "0301")], [a])
        self.assertEqual(ledger.session_in_progress(self.items(), "0301", exclude=a), [])


if __name__ == "__main__":
    unittest.main()
