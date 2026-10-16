"""اختباراتُ preview_batch (W-20261014-010) — unittest بلا اعتمادٍ خارجيّ:  python -m unittest test_preview_batch"""

import subprocess
import unittest
from pathlib import Path

import preview_batch as pb

INTEGRATE = """التكامل:      مفعَّل
الخطّة:       تكامل@96ba3a8 (main@25cef9a + 2 فرعاً)
    + w015-grid-live — 1 إيداعاً (آخرُها 10-14 20:50)
    + pr-1067 «W-20261011-008: أداة» — 3 إيداعاً (آخرُها 10-12 18:02)
    ✗ w014-period-variety — خاملٌ: آخرُ إيداعٍ جديدٍ فيه منذ 12 يوماً (سقفُ التكامل 48 ساعة)
    ✗ shschool_mvp — تعارضٌ مع main
"""


def card(state="ready_for_review", **kw):
    return {"state": state, "held_by": "0401", "problem": "مشكلة", **kw}


class Parse(unittest.TestCase):
    def test_shown_and_blocked_are_split(self):
        shown, blocked = pb.parse_integrate(INTEGRATE)
        self.assertEqual(shown, {"w015-grid-live", "pr-1067"})
        self.assertIn("خاملٌ", blocked["w014-period-variety"])
        self.assertEqual(blocked["shschool_mvp"], "تعارضٌ مع main")


class Classify(unittest.TestCase):
    def setUp(self):
        self.shown, self.blocked = pb.parse_integrate(INTEGRATE)

    def test_three_sections(self):
        items = {
            "A": card(branch="claude/w015-grid-live"),
            "B": card(branch="w014-period-variety"),
            "C": card(branch="never-committed"),
        }
        rows = {r["id"]: r for r in pb.build_rows(items, self.shown, self.blocked)}
        self.assertEqual(rows["A"]["section"], pb.AUTO)
        self.assertEqual(rows["B"]["section"], pb.BLOCKED)
        self.assertIn("خاملٌ", rows["B"]["why"])
        self.assertEqual(rows["C"]["section"], pb.PIN)

    def test_card_without_branch_needs_pin_not_guessed(self):
        row = pb.build_rows({"A": card()}, self.shown, self.blocked)[0]
        self.assertEqual(row["section"], pb.PIN)

    def test_only_ready_for_review_enters(self):
        items = {"A": card(branch="w015-grid-live"), "B": card("approved", branch="w015-grid-live")}
        self.assertEqual([r["id"] for r in pb.build_rows(items, self.shown, self.blocked)], ["A"])

    def test_missing_preview_fields_are_marked_not_invented(self):
        row = pb.build_rows({"A": card(branch="w015-grid-live")}, self.shown, self.blocked)[0]
        for f in pb.FIELDS:
            self.assertEqual(row[f], pb.MISSING)

    def test_preview_fields_are_carried(self):
        pv = {"url": "http://localhost:8500/x/", "role": "مدير", "username": "10001", "severity": "P1", "head": "ab12cd34"}
        row = pb.build_rows({"A": card(branch="w015-grid-live", preview=pv)}, self.shown, self.blocked)[0]
        for f, v in pv.items():
            self.assertEqual(row[f], v)


class Render(unittest.TestCase):
    def test_sheet_has_three_sections_missing_marker_and_no_approval_claim(self):
        shown, blocked = pb.parse_integrate(INTEGRATE)
        rows = pb.build_rows({"A": card(branch="w015-grid-live")}, shown, blocked)
        page = pb.render_html(rows, {"median": 1.0, "mean": 12.1, "p90": 20.0, "n": 93}, "2026-10-14")
        for key in (pb.AUTO, pb.PIN, pb.BLOCKED):
            self.assertIn(pb.TITLES[key], page)
        self.assertIn("ناقص", page)
        self.assertIn("الاعتمادُ للمالك وحدَه", page)
        self.assertIn("الوسيط: نصف البطاقات", page)  # كلّ رقمٍ بمعناه

    def test_html_is_escaped(self):
        rows = [{"id": "<b>", "section": pb.AUTO, "why": "<x>", "holder": "0", "problem": "<script>", **{f: "&" for f in pb.FIELDS}}]
        page = pb.render_html(rows, {"n": 0}, "t")
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)


class Baseline(unittest.TestCase):
    def test_review_to_approve_stats(self):
        def ev(ts, i, kind, state=None):
            return {"ts": ts, "id": i, "kind": kind, "data": {"state": state} if state else {}}

        events = []
        for i, mins in enumerate((30, 60, 600), 1):
            cid = f"W-{i}"
            hh, mm = divmod(mins, 60)
            events += [ev("2026-09-29T08:00:00+03:00", cid, "created"),
                       ev("2026-09-29T09:00:00+03:00", cid, "state", "ready_for_review"),
                       ev(f"2026-09-29T{9 + hh:02d}:{mm:02d}:00+03:00", cid, "state", "approved")]
        b = pb.baseline(events)
        self.assertEqual(b["n"], 3)
        self.assertEqual(b["median"], 1.0)
        self.assertEqual(b["p90"], 10.0)

    def test_empty_ledger_is_unmeasured(self):
        self.assertEqual(pb.baseline([]), {"n": 0})


class ReadOnly(unittest.TestCase):
    def test_tool_never_calls_mutating_preview_commands(self):
        src = Path(pb.__file__).read_text(encoding="utf-8")
        for bad in (" pin", " release", " up", " down", " watch", "integrate on", "integrate off", "exclude", "include"):
            self.assertNotIn(f'"preview.sh", "{bad.strip()}"', src)
        self.assertIn('"bash", "scripts/preview.sh", "integrate"]', src)

    def test_integrate_is_run_with_no_arguments(self):
        calls = []

        def fake(cmd, **kw):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="x", stderr="")

        orig = pb.subprocess.run
        pb.subprocess.run = fake
        try:
            pb.run_integrate("D:/x")
        finally:
            pb.subprocess.run = orig
        self.assertEqual(calls, [["bash", "scripts/preview.sh", "integrate"]])


if __name__ == "__main__":
    unittest.main()
