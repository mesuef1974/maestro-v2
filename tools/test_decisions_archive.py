"""اختباراتُ أرشفة القرارات:  python -m pytest test_decisions_archive.py"""

import tempfile
import unittest
from pathlib import Path

import decision_add
import decisions_archive as da

TEXT = (
    "# سجلّ\n> رأس\n\n"
    "- D-01 | 09-26 ~17:00 | قديم | أثر | مرجع\n"
    "  سطرُ متابعةٍ للقديم\n"
    "- D-02 | 10-20 10:00 | جديد | أثر | مرجع\n"
    "- D-03 | بلا تاريخ | غيرُ مقروء | أثر | مرجع\n"
    "## D-04م (09-27): عنوانٌ قديم\nمتنُه\n"
)


class Split(unittest.TestCase):
    def test_old_entries_move_with_their_continuation_and_nothing_is_lost(self):
        keep, moved, ids = da.split(TEXT, "10-11")
        self.assertEqual(ids, ["D-01م", "D-04م"])
        self.assertIn("سطرُ متابعةٍ للقديم", moved)
        self.assertIn("متنُه", moved)
        self.assertEqual(sorted((keep + moved).splitlines()), sorted(TEXT.splitlines()))

    def test_header_new_and_unreadable_date_stay_live(self):
        keep, _, _ = da.split(TEXT, "10-11")
        for s in ("# سجلّ", "D-02", "D-03"):
            self.assertIn(s, keep)

    def test_pinned_stays_live(self):
        keep, _, ids = da.split(TEXT, "10-11", frozenset({"D-01م"}))
        self.assertNotIn("D-01م", ids)
        self.assertIn("سطرُ متابعةٍ للقديم", keep)


class Apply(unittest.TestCase):
    def test_apply_is_idempotent_and_keeps_numbers_reserved(self):
        tmp = Path(tempfile.mkdtemp())
        live, arch = tmp / "decisions.md", tmp / "decisions_archive.md"
        live.write_text(TEXT, encoding="utf-8")
        self.assertEqual(da.apply("10-11", live, arch)[0], 2)
        after = live.read_text(encoding="utf-8"), arch.read_text(encoding="utf-8")
        self.assertEqual(da.apply("10-11", live, arch), (0, 0))
        self.assertEqual((live.read_text(encoding="utf-8"), arch.read_text(encoding="utf-8")), after)
        old = decision_add.DECISIONS
        try:
            decision_add.DECISIONS = live
            arch.write_text(arch.read_text(encoding="utf-8") + "- D-90م | 09-01 | قديم | أ | م\n", encoding="utf-8")
            self.assertEqual(decision_add.next_id(), "D-91م")
        finally:
            decision_add.DECISIONS = old

    def test_all_text_reads_archive_first(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "decisions_archive.md").write_text("A\n", encoding="utf-8")
        (tmp / "decisions.md").write_text("B\n", encoding="utf-8")
        self.assertLess(da.all_text(tmp).index("A"), da.all_text(tmp).index("B"))


if __name__ == "__main__":
    unittest.main()
