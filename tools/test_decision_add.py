"""اختباراتُ decision_add.py — على مجلّدٍ مؤقّتٍ لا على decisions.md الحقيقيّ أبداً."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import decision_add as m  # noqa: E402


class DecisionAddTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "decisions.md").write_text("# اختبار\n", encoding="utf-8")
        self._root, self._dec, self._meta = m.ROOT, m.DECISIONS, m.META
        m.ROOT = self.tmp
        m.DECISIONS = self.tmp / "decisions.md"
        m.META = self.tmp / "ledger" / "decisions_meta.jsonl"

    def tearDown(self):
        m.ROOT, m.DECISIONS, m.META = self._root, self._dec, self._meta
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_add_writes_row_and_meta(self):
        rc = m.cmd_add(argparse.Namespace(text="نصٌّ", effect="أثرٌ", reference="مرجعٌ"))
        self.assertEqual(rc, 0)
        text = m.DECISIONS.read_text(encoding="utf-8")
        self.assertIn("D-1م", text)
        self.assertIn("نصٌّ | أثرٌ | مرجعٌ", text)
        meta = json.loads(m.META.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(meta["type"], "structural")

    def test_ids_increment_from_existing_file(self):
        m.DECISIONS.write_text("- D-9م | 01-01 00:00 | س | ص | ع\n", encoding="utf-8")
        m.cmd_add(argparse.Namespace(text="جديد", effect="-", reference="-"))
        self.assertIn("D-10م", m.DECISIONS.read_text(encoding="utf-8"))

    def test_approval_carries_verbatim_text_untouched(self):
        verbatim = "نعم، اعتمدتُ هذا بالضبط"
        m.cmd_approval(argparse.Namespace(text=verbatim, location="محادثةُ الاختبار", effect="", reference=""))
        self.assertIn(f"«{verbatim}»", m.DECISIONS.read_text(encoding="utf-8"))

    def test_non_automatable_rejects_without_reason(self):
        rc = m.cmd_non_automatable(argparse.Namespace(
            text="س", category="تشغيلي", reason="", alternative="بديل", reference=""))
        self.assertEqual(rc, 1)
        self.assertNotIn("D-1م", m.DECISIONS.read_text(encoding="utf-8"))

    def test_non_automatable_rejects_without_alternative(self):
        rc = m.cmd_non_automatable(argparse.Namespace(
            text="س", category="تشغيلي", reason="سبب", alternative="", reference=""))
        self.assertEqual(rc, 1)

    def test_non_automatable_rejects_bad_category(self):
        rc = m.cmd_non_automatable(argparse.Namespace(
            text="س", category="غير هذا", reason="سبب", alternative="بديل", reference=""))
        self.assertEqual(rc, 1)

    def test_non_automatable_review_dates_by_category(self):
        m.cmd_non_automatable(argparse.Namespace(
            text="س", category="تشغيلي", reason="سبب", alternative="بديل", reference=""))
        meta = json.loads(m.META.read_text(encoding="utf-8").splitlines()[0])
        due = datetime.fromisoformat(meta["review_due"]) - datetime.fromisoformat(meta["ts"])
        self.assertEqual(due.days, 90)

        m.META.unlink()
        m.cmd_non_automatable(argparse.Namespace(
            text="س", category="بصري", reason="سبب", alternative="بديل", reference=""))
        meta = json.loads(m.META.read_text(encoding="utf-8").splitlines()[0])
        due = datetime.fromisoformat(meta["review_due"]) - datetime.fromisoformat(meta["ts"])
        self.assertEqual(due.days, 60)

    def test_coverage_counts_overdue_and_missing_reason(self):
        m.append_meta({"id": "D-1م", "type": "non_automatable", "reason": "سبب",
                        "ts": datetime.now().isoformat(),
                        "review_due": (datetime.now() - timedelta(days=1)).isoformat(),
                        "reviewed": False})
        m.append_meta({"id": "D-2م", "type": "non_automatable", "reason": "",
                        "ts": datetime.now().isoformat(),
                        "review_due": (datetime.now() + timedelta(days=10)).isoformat(),
                        "reviewed": False})
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            m.cmd_coverage(None)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["non_automatable_count"], 2)
        self.assertEqual(out["overdue_review_count"], 1)
        self.assertEqual(out["missing_reason_count"], 1)
        # الملخّصُ رقميٌّ فقط — لا نصَّ قرارٍ واحد يظهر فيه
        self.assertNotIn("سبب", buf.getvalue())

    def test_coverage_on_empty_meta(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            m.cmd_coverage(None)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["non_automatable_count"], 0)


if __name__ == "__main__":
    unittest.main()
