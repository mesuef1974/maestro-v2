"""اختباراتُ batch_report (W-20261016-028) — بدفترٍ تجريبيّ بلا شبكة:  python -m unittest tools.test_batch_report"""

import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import batch_report as br  # noqa: E402

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)


def ev(cid, state, ts, **data):
    return {"ts": ts, "kind": "state", "id": cid, "data": {"state": state, "by": "t", **data}}


def create(cid, ts="2026-10-16T00:00:00+00:00"):
    return {"ts": ts, "kind": "created", "id": cid, "data": {"problem": "p", "priority": "P1"}}


class Matching(unittest.TestCase):
    def test_explicit_code_only(self):
        self.assertEqual(br.explicit_code({"title": "W-20261016-014: x"}), "W-20261016-014")
        self.assertEqual(br.explicit_code({"headRefName": "claude/x", "body": "يخصّ W-20261016-020"}), "W-20261016-020")

    def test_no_code_or_ambiguous_is_not_attributed(self):
        # حالتا #913 و#940: طلبٌ بلا رمزٍ أو بأكثر من رمزٍ لا يُنسب لأيّ بطاقة
        self.assertIsNone(br.explicit_code({"title": "إصلاح الجدول", "body": "قريب من الجدول"}))
        self.assertIsNone(br.explicit_code({"title": "W-20261016-014 و W-20261016-015"}))
        self.assertEqual(br.match_prs([{"number": 913, "title": "بلا رمز"}]), {})


class Report(unittest.TestCase):
    def events(self):
        return [
            create("W-1"), ev("W-1", "ready_for_review", "2026-10-16T08:00:00+00:00"),
            ev("W-1", "approved", "2026-10-16T10:00:00+00:00", head="aaaaaaaa"),
            create("W-2"), ev("W-2", "ready_for_review", "2026-10-16T09:00:00+00:00"),
        ]

    def test_numbers_match_independent_count(self):
        rep = br.build(self.events(), [{"number": 5, "title": "W-1 مثال W-20261016-001"}], 7, NOW)
        ids = [c["id"] for c in rep["cards"]]
        self.assertEqual(ids, ["W-1", "W-2"])
        ind = rep["indicators"]
        self.assertEqual(ind["owner_queue"], 1)  # W-2 وحدها جاهزة
        self.assertEqual(ind["ready_to_approve_median_h"], 2.0)  # 08:00 ← 10:00
        self.assertEqual(ind["ready_to_approve_n"], 1)
        self.assertEqual(ind["reapprovals"], 0)

    def test_gh_missing_marks_unmeasured(self):
        rep = br.build(self.events(), None, 7, NOW)
        self.assertEqual(rep["prs_source"], br.UNMEASURED)
        self.assertTrue(all(c["prs"] == br.UNMEASURED for c in rep["cards"]))

    def test_html_is_rtl_arabic_and_defines_every_number(self):
        rep = br.build(self.events(), None, 7, NOW)
        page = br.render_html(rep)
        self.assertIn('dir="rtl"', page)
        self.assertIn('lang="ar"', page)
        for text in br.DEFINITIONS.values():
            self.assertIn(text, page)
        self.assertIn(br.UNMEASURED, page)

    def test_json_and_html_written_with_same_numbers(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(br.ledger, "load_events", return_value=self.events()), \
                mock.patch.object(br, "fetch_prs", return_value=[]):
            self.assertEqual(br.main(["--out", str(Path(d) / "r")]), 0)
            data = json.loads((Path(d) / "r.json").read_text(encoding="utf-8"))
            page = (Path(d) / "r.html").read_text(encoding="utf-8")
        self.assertIn(str(data["indicators"]["owner_queue"]), page)
        self.assertIn(str(data["indicators"]["ready_to_approve_median_h"]), page)


if __name__ == "__main__":
    unittest.main()
